from lib import db
from lib.sources import parse_google, parse_youtube


def test_first_insert_stays_new_until_marked(tmp_path, monkeypatch):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    conn = db.connect()
    ts = db.now()
    row = {
        "kind": "person",
        "platform": "youtube",
        "handle": "ada",
        "name": "Ada",
        "url": "https://youtube.com/@ada",
        "score": 10,
        "hit_count": 1,
        "views": 100,
        "likes": 1,
        "comments": 0,
        "sample": "hello",
        "sample_url": "https://youtu.be/1",
    }
    assert db.upsert_entity(conn, row, "ai video", ts, "creators") == "new"
    row["score"] = 20
    assert db.upsert_entity(conn, row, "ai video", ts, "creators") == "new"
    assert db.mark(conn, "person", "youtube", "ada", "outreached")
    row["score"] = 30
    assert db.upsert_entity(conn, row, "ai video", ts, "creators") == "known"
    got = db.get_entity(conn, "person", "youtube", "ada")
    assert got["status"] == "outreached"
    assert got["score"] == 30
    assert got["previous_score"] == 20
    conn.close()


def test_person_and_company_same_slug_are_two_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    conn = db.connect()
    ts = db.now()
    db.upsert_entity(
        conn,
        {"kind": "person", "platform": "linkedin", "handle": "acme", "name": "Pat Acme"},
        "q",
        ts,
        "people",
    )
    db.upsert_entity(
        conn,
        {"kind": "company", "platform": "linkedin", "handle": "acme", "name": "Acme Inc"},
        "q",
        ts,
        "companies",
    )
    assert db.get_entity(conn, "person", "linkedin", "acme")["name"] == "Pat Acme"
    assert db.get_entity(conn, "company", "linkedin", "acme")["name"] == "Acme Inc"
    conn.close()


def test_export_import_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    conn = db.connect()
    ts = db.now()
    db.seed(
        conn,
        {"kind": "person", "platform": "tiktok", "handle": "skipme", "status": "skip", "name": "Skip"},
        ts,
    )
    text = db.export_csv(db.list_entities(conn, status="skip"))
    assert "skipme" in text
    conn.close()

    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path / "other"))
    conn2 = db.connect()
    n = db.import_csv(conn2, text, ts)
    assert n == 1
    got = db.get_entity(conn2, "person", "tiktok", "skipme")
    assert got["status"] == "skip"
    conn2.close()


def test_youtube_channel_handle_and_views():
    hits = parse_youtube(
        {
            "videos": [
                {
                    "id": "abc",
                    "title": "Runway tutorial",
                    "url": "https://www.youtube.com/watch?v=abc",
                    "viewCountInt": 1200,
                    "likeCount": 40,
                    "commentCount": 8,
                    "channel": {"handle": "maya", "title": "Maya Makes"},
                }
            ]
        },
        10,
    )
    assert len(hits) == 1
    assert hits[0]["handle"] == "maya"
    assert hits[0]["views"] == 1200
    assert hits[0]["score"] > 1200


def test_google_people_skips_company_pages():
    hits = parse_google(
        {
            "results": [
                {"url": "https://www.linkedin.com/company/acme", "title": "Acme"},
                {
                    "url": "https://www.linkedin.com/in/ada-lovelace",
                    "title": "Ada Lovelace | LinkedIn",
                    "description": "founder",
                },
            ]
        },
        10,
        source="linkedin_people",
        scenario_kind="person",
    )
    assert len(hits) == 1
    assert hits[0]["handle"] == "ada-lovelace"
    assert hits[0]["kind"] == "person"
    assert hits[0]["score"] == 0
