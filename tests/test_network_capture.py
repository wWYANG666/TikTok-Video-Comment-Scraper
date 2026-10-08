from app.crawler.network_capture import (
    TikTokNetworkCapture,
    parse_comment_payload,
    parse_video_payload,
)


def test_parse_video_payload_supports_tiktok_fields() -> None:
    payload = {
        "data": [
            {
                "type": 1,
                "item": {
                    "id": "7412345678901234567",
                    "desc": "Root canal treatment explained",
                    "createTime": 1_725_000_000,
                    "author": {"uniqueId": "demo_dentist"},
                    "video": {
                        "cover": {"urlList": ["https://example.com/cover.jpg"]}
                    },
                    "stats": {
                        "diggCount": 1200,
                        "commentCount": 86,
                        "shareCount": 33,
                    },
                },
            }
        ]
    }

    videos = parse_video_payload(payload)

    assert len(videos) == 1
    assert videos[0].video_id == "7412345678901234567"
    assert videos[0].author_name == "demo_dentist"
    assert videos[0].like_count == 1200
    assert videos[0].comment_count == 86
    assert videos[0].cover_url == "https://example.com/cover.jpg"


def test_parse_comments_preserves_reply_relationship() -> None:
    payload = {
        "comments": [
            {
                "cid": "comment-1",
                "text": "Does it hurt?",
                "digg_count": 12,
                "create_time": 1_725_000_000,
                "user": {"unique_id": "viewer_one"},
                "reply_comment": [
                    {
                        "cid": "reply-1",
                        "text": "Local anaesthetic is normally used.",
                        "digg_count": 3,
                        "user": {"unique_id": "demo_dentist"},
                    }
                ],
            }
        ]
    }

    comments = {item.comment_id: item for item in parse_comment_payload(payload)}

    assert comments["comment-1"].parent_comment_id is None
    assert comments["reply-1"].parent_comment_id == "comment-1"
    assert comments["reply-1"].author_name == "demo_dentist"


def test_reply_endpoint_uses_request_parent_id() -> None:
    payload = {
        "comments": [
            {
                "cid": "reply-2",
                "text": "A second detailed answer.",
                "user": {"unique_id": "demo_dentist"},
            }
        ]
    }

    comments = parse_comment_payload(payload, fallback_parent_id="comment-1")

    assert comments[0].parent_comment_id == "comment-1"


def test_comment_limits_are_applied_per_thread(tmp_path) -> None:
    capture = TikTokNetworkCapture(tmp_path)
    capture.comments_by_video["video-1"] = {
        "comment-1": parse_comment_payload(
            {"comments": [{"cid": "comment-1", "text": "Top level"}]}
        )[0],
        "reply-1": parse_comment_payload(
            {"comments": [{"cid": "reply-1", "text": "First reply"}]},
            fallback_parent_id="comment-1",
        )[0],
        "reply-2": parse_comment_payload(
            {"comments": [{"cid": "reply-2", "text": "Second reply"}]},
            fallback_parent_id="comment-1",
        )[0],
    }

    comments = capture.get_comments("video-1", max_comments=1, max_replies=1)

    assert [comment.comment_id for comment in comments] == ["comment-1", "reply-1"]


def test_reply_request_parameters_are_detected() -> None:
    url = (
        "https://www.tiktok.com/api/comment/list/reply/"
        "?aweme_id=video-1&comment_id=comment-1&cursor=0"
    )

    assert TikTokNetworkCapture._classify(url) == "comments"
    assert TikTokNetworkCapture._video_id_from_url(url) == "video-1"
    assert TikTokNetworkCapture._parent_comment_id_from_url(url) == "comment-1"
