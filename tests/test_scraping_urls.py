from waybackmachine.scraping.urls import ensure_wayback_url


def test_ensure_wayback_url_rewrites_original_site_link():
    current = "https://web.archive.org/web/20160111013726/http://www.fullsizechevy.com/forum/forum.php"
    link = "http://www.fullsizechevy.com/forum/market-place-preferred-vendors/"
    got = ensure_wayback_url(current, link)
    assert got.startswith("https://web.archive.org/web/20160111013726/")
    assert "market-place-preferred-vendors" in got


def test_ensure_wayback_url_keeps_relative_link_on_archive():
    current = "https://web.archive.org/web/20160111013726/http://www.fullsizechevy.com/forum/forum.php"
    link = "site-links/"
    got = ensure_wayback_url(current, link)
    assert got.startswith("https://web.archive.org/web/20160111013726/")
    assert "site-links" in got


def test_ensure_wayback_url_leaves_already_wayback_unchanged():
    current = "https://web.archive.org/web/20160111013726/http://www.fullsizechevy.com/forum/"
    link = "https://web.archive.org/web/20160103142504/http://www.fullsizechevy.com/forum/site-links/"
    got = ensure_wayback_url(current, link)
    assert got == link
