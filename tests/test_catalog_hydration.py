import unittest

from douban_recommender.models import MediaItem

try:
    from douban_recommender.catalog_hydration import CatalogHydrationCoordinator, metadata_quality
except ImportError:  # RED: implementation intentionally absent at first.
    CatalogHydrationCoordinator = None
    metadata_quality = None


class Record:
    def __init__(self, key, item, state="candidate", updated_at=0.0):
        self.item_key = key
        self.item = item
        self.state = state
        self.updated_at = updated_at


class Repository:
    def __init__(self, records):
        self.records = records

    def library_records(self):
        return list(self.records)


class Service:
    def __init__(self, records):
        self.repository = Repository(records)


class Api:
    def __init__(self, records):
        self.service = Service(records)
        self.calls = []

    def enrich_title(self, key):
        self.calls.append(key)
        record = next(record for record in self.service.repository.records if record.item_key == key)
        record.item.summary = "补齐后的真实简介。"
        record.item.genres = ["剧情"]
        record.item.douban_rating = 8.8
        record.item.directors = ["导演甲"]
        record.item.casts = ["演员乙"]
        record.item.raw["stills"] = ["https://img1.doubanio.com/view/photo/l/public/p1.jpg"]
        record.item.raw["people_photos"] = {
            "导演甲": "https://img1.doubanio.com/view/celebrity/m/public/director.jpg",
            "演员乙": "https://img1.doubanio.com/view/celebrity/m/public/actor.jpg",
        }
        return {"item_key": key}


def complete_item(title="完整作品"):
    return MediaItem(
        title=title,
        douban_id="100",
        media_type="电影",
        summary="完整且真实的剧情简介。",
        genres=["剧情"],
        douban_rating=8.5,
        directors=["导演甲"],
        casts=["演员乙"],
        raw={
            "stills": ["https://img1.doubanio.com/view/photo/l/public/p1.jpg"],
            "people_photos": {
                "导演甲": "https://img1.doubanio.com/view/celebrity/m/public/director.jpg",
                "演员乙": "https://img1.doubanio.com/view/celebrity/m/public/actor.jpg",
            },
        },
    )


class CatalogHydrationTests(unittest.TestCase):
    def test_default_background_hydration_waits_until_the_initial_catalog_is_interactive(self):
        coordinator = CatalogHydrationCoordinator(Api([]), start_thread=False)

        self.assertGreaterEqual(coordinator.initial_delay_seconds, 20.0)

        coordinator.close()

    def test_metadata_quality_requires_decision_data_and_real_visuals(self):
        item = MediaItem(
            title="待补作品",
            douban_id="42",
            media_type="电影",
            summary="正在补齐这部电影的剧情简介；目前已确认类型为电影。",
            genres=["电影"],
            directors=[],
            casts=[],
            raw={},
        )

        quality = metadata_quality(item)

        self.assertFalse(quality["complete"])
        self.assertEqual(
            {"summary", "genres", "rating", "people", "stills"},
            set(quality["missing"]),
        )

    def test_metadata_quality_keeps_largely_english_synopsis_in_the_localization_queue(self):
        item = complete_item("英文简介待本地化")
        item.summary = (
            "Historian Dominic Sandbrook and leading creators tell the story "
            "of science fiction across television and cinema."
        )

        quality = metadata_quality(item)

        self.assertFalse(quality["complete"])
        self.assertIn("summary", quality["missing"])

    def test_run_once_prioritizes_personal_library_and_skips_complete_records(self):
        watched = Record(
            "douban:watched",
            MediaItem(title="看过但待补", douban_id="101", media_type="电影", raw={}),
            state="watched",
        )
        candidate = Record(
            "douban:candidate",
            MediaItem(title="候选但待补", douban_id="102", media_type="电影", raw={}),
            state="candidate",
        )
        complete = Record("douban:complete", complete_item(), state="watched")
        api = Api([candidate, complete, watched])
        coordinator = CatalogHydrationCoordinator(
            api,
            batch_size=1,
            max_workers=1,
            start_thread=False,
        )

        status = coordinator.run_once()

        self.assertEqual(["douban:watched"], api.calls)
        self.assertEqual(3, status["total"])
        self.assertEqual(2, status["complete"])
        self.assertEqual(1, status["pending"])
        self.assertEqual(1, status["succeeded"])
        coordinator.close()

    def test_metadata_quality_requires_real_primary_people_portraits(self):
        item = complete_item("人物肖像待补")
        item.raw["people_photos"] = {
            "导演甲": "https://img1.doubanio.com/f/vendors/pics/personage-default-medium.png",
            "演员乙": "https://img1.doubanio.com/view/celebrity/m/public/actor.jpg",
        }

        quality = metadata_quality(item)

        self.assertFalse(quality["complete"])
        self.assertIn("people", quality["missing"])

    def test_metadata_quality_does_not_require_portraits_for_every_secondary_credit(self):
        item = complete_item("主创肖像完整")
        item.directors = ["导演甲", "副导演丙"]
        item.casts = ["演员乙", "演员丁", "演员戊", "演员己", "演员庚", "演员辛", "演员壬"]
        item.raw["people_photos"] = {
            name: f"https://img1.doubanio.com/view/celebrity/m/public/{index}.jpg"
            for index, name in enumerate(["导演甲", "演员乙", "演员丁", "演员戊", "演员己", "演员庚"])
        }

        quality = metadata_quality(item)

        self.assertTrue(quality["complete"])


if __name__ == "__main__":
    unittest.main()
