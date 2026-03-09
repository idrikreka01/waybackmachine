import logging
import threading
import time
from typing import Any

from selenium.common.exceptions import NoSuchWindowException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC  # noqa: N812
from selenium.webdriver.support.ui import WebDriverWait

from waybackmachine.config import (
    BROWSER_PAGE_LOAD_TIMEOUT,
    BROWSER_WAIT_TIMEOUT,
    CHROME_VERSION_MAIN,
    COOLDOWN_BACKOFF_SECONDS,
    COOLDOWN_EXTRA_ATTEMPTS,
    HEADLESS,
    REQUEST_DELAY,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_BASE,
    USE_WEBDRIVER_MANAGER,
)

LOG = logging.getLogger(__name__)

STABILITY_CHECK_TIMEOUT = 15.0

_driver_creation_lock = threading.Lock()
_desktop_ua_cache: list[str] | None = None


def _get_desktop_ua(worker_index: int) -> str:
    global _desktop_ua_cache
    if _desktop_ua_cache is None:
        from fake_useragent import UserAgent

        ua = UserAgent()
        getters = ["chrome", "firefox", "safari", "edge"]
        _desktop_ua_cache = []
        for i in range(10):
            key = getters[i % len(getters)]
            try:
                _desktop_ua_cache.append(getattr(ua, key))
            except Exception:
                try:
                    _desktop_ua_cache.append(ua.chrome)
                except Exception:
                    _desktop_ua_cache.append(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
    return _desktop_ua_cache[worker_index % len(_desktop_ua_cache)]


def _driver_stability_check(driver: WebDriver) -> None:
    driver.get("about:blank")
    WebDriverWait(driver, STABILITY_CHECK_TIMEOUT).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )


def create_driver(worker_index: int | None = None) -> WebDriver:
    import undetected_chromedriver as uc

    with _driver_creation_lock:
        for attempt in range(2):
            options = uc.ChromeOptions()
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            if worker_index is not None:
                options.add_argument(f"--user-agent={_get_desktop_ua(worker_index)}")
            if HEADLESS:
                options.add_argument("--headless=new")
            kwargs: dict[str, Any] = {"options": options}
            if CHROME_VERSION_MAIN is not None:
                kwargs["version_main"] = CHROME_VERSION_MAIN
            if USE_WEBDRIVER_MANAGER:
                from webdriver_manager.chrome import ChromeDriverManager

                kwargs["driver_executable_path"] = ChromeDriverManager().install()
            driver = uc.Chrome(**kwargs)
            driver.set_page_load_timeout(BROWSER_PAGE_LOAD_TIMEOUT)
            try:
                _driver_stability_check(driver)
                return driver
            except (NoSuchWindowException, WebDriverException) as e:
                try:
                    driver.quit()
                except Exception:
                    pass
                if attempt == 0:
                    LOG.warning("Chrome closed during startup check, retrying driver creation once")
                    continue
                hint = " Set HEADLESS=false in .env to avoid headless crashes." if HEADLESS else ""
                raise RuntimeError(
                    f"Chrome closed immediately after launch.{hint} Run again or set HEADLESS=false in .env."
                ) from e
        raise RuntimeError("create_driver failed")


def _is_cooldown_error(exc: BaseException) -> bool:
    msg = (getattr(exc, "msg", None) or str(exc)).lower()
    return (
        "timeout" in msg
        or "timed out" in msg
        or "err_connection" in msg
        or "connection refused" in msg
        or "connection reset" in msg
    )


def get_page_html(driver: WebDriver, url: str) -> str:
    if REQUEST_DELAY > 0:
        time.sleep(REQUEST_DELAY)
    last_exc: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            driver.get(url)
            WebDriverWait(driver, BROWSER_WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(1.0)
            return driver.page_source or ""
        except NoSuchWindowException as e:
            hint = (
                " HEADLESS=true often causes this; set HEADLESS=false in .env." if HEADLESS else ""
            )
            LOG.error(
                "Browser window closed (Chrome may have crashed).%s",
                hint,
                extra={"url": url},
            )
            raise RuntimeError(
                f"Browser window closed.{hint} Set HEADLESS=false in .env or run again."
            ) from e
        except WebDriverException as e:
            last_exc = e
            if attempt < RETRY_ATTEMPTS - 1:
                delay = RETRY_BACKOFF_BASE**attempt
                LOG.warning(
                    "Browser request failed, backing off",
                    extra={
                        "url": url,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "delay_s": delay,
                    },
                )
                time.sleep(delay)
            else:
                break
    if last_exc and _is_cooldown_error(last_exc) and COOLDOWN_EXTRA_ATTEMPTS > 0:
        for cooldown_attempt in range(COOLDOWN_EXTRA_ATTEMPTS):
            LOG.warning(
                "Cooldown backoff: pausing %.0fs then retrying (attempt %s/%s)",
                COOLDOWN_BACKOFF_SECONDS,
                cooldown_attempt + 1,
                COOLDOWN_EXTRA_ATTEMPTS,
                extra={"url": url},
            )
            time.sleep(COOLDOWN_BACKOFF_SECONDS)
            try:
                if REQUEST_DELAY > 0:
                    time.sleep(REQUEST_DELAY)
                driver.get(url)
                WebDriverWait(driver, BROWSER_WAIT_TIMEOUT).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(1.0)
                return driver.page_source or ""
            except (NoSuchWindowException, WebDriverException) as e:
                last_exc = e
                if cooldown_attempt < COOLDOWN_EXTRA_ATTEMPTS - 1:
                    continue
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("get_page_html exhausted retries")
