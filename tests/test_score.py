from lib.score import apply_flags, entity_score, hit_score, title_flags


def test_comments_outweigh_views():
    assert hit_score(views=100, comments=2) > hit_score(views=100, comments=0)


def test_compilation_downrank():
    assert "compilation" in title_flags("Best of AI ads compilation 2026")
    hit = apply_flags({"title": "lofi mix 10 hours", "score": 1000})
    assert hit["score"] == 200


def test_presence_score_when_no_engagement():
    hits = [
        {"views": 0, "likes": 0, "comments": 0, "shares": 0, "flags": []},
        {"views": 0, "likes": 0, "comments": 0, "shares": 0, "flags": []},
    ]
    stats = entity_score(hits, "people")
    assert stats["score"] == 20
    assert stats["hit_count"] == 2


def test_creators_use_engagement_not_presence():
    hits = [{"views": 0, "likes": 0, "comments": 0, "shares": 0, "flags": []}]
    stats = entity_score(hits, "creators")
    assert stats["score"] == 0
