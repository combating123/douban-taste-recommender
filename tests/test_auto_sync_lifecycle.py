import unittest
from unittest import mock

import douban_recommender.web as web_module


class AutoSyncLifecycleTests(unittest.TestCase):
    def test_main_initializes_sync_before_server_and_closes_it_before_server_on_error(self):
        events = []
        sync_api = mock.Mock()
        server = mock.Mock()

        def get_sync_api():
            events.append("sync.get")
            return sync_api

        def create_server(*_args):
            events.append("server.create")
            return server

        def serve_forever():
            events.append("server.serve_forever")
            raise RuntimeError("serve failed")

        sync_api.close.side_effect = lambda: events.append("sync.close")
        server.serve_forever.side_effect = serve_forever
        server.server_close.side_effect = lambda: events.append("server.server_close")

        with (
            mock.patch.object(web_module, "get_sync_api", side_effect=get_sync_api) as get_sync_api_mock,
            mock.patch.object(web_module, "ThreadingHTTPServer", side_effect=create_server) as server_factory,
        ):
            with self.assertRaisesRegex(RuntimeError, "serve failed"):
                web_module.main(["--host", "127.0.0.1", "--port", "8123", "--no-browser"])

        self.assertEqual(
            events,
            [
                "sync.get",
                "server.create",
                "server.serve_forever",
                "sync.close",
                "server.server_close",
            ],
        )
        get_sync_api_mock.assert_called_once_with()
        server_factory.assert_called_once_with(("127.0.0.1", 8123), web_module.Handler)
        server.serve_forever.assert_called_once_with()
        sync_api.close.assert_called_once_with()
        server.server_close.assert_called_once_with()

    def test_main_reuses_injected_global_sync_api_without_building_or_closing_twice(self):
        events = []
        injected_sync_api = mock.Mock()
        server = mock.Mock()
        original_sync_api = web_module.SYNC_API
        original_get_sync_api = web_module.get_sync_api

        def get_injected_sync_api():
            events.append("sync.get")
            return original_get_sync_api()

        def create_server(*_args):
            events.append("server.create")
            return server

        server.serve_forever.side_effect = lambda: events.append("server.serve_forever")
        injected_sync_api.close.side_effect = lambda: events.append("sync.close")
        server.server_close.side_effect = lambda: events.append("server.server_close")
        web_module.SYNC_API = injected_sync_api
        try:
            with (
                mock.patch.object(web_module, "get_sync_api", side_effect=get_injected_sync_api) as get_sync_api_mock,
                mock.patch.object(web_module, "build_default_sync_api") as build_default_sync_api,
                mock.patch.object(web_module, "ThreadingHTTPServer", side_effect=create_server),
            ):
                result = web_module.main(["--no-browser"])
        finally:
            web_module.SYNC_API = original_sync_api

        self.assertEqual(result, 0)
        self.assertEqual(
            events,
            [
                "sync.get",
                "server.create",
                "server.serve_forever",
                "sync.close",
                "server.server_close",
            ],
        )
        get_sync_api_mock.assert_called_once_with()
        build_default_sync_api.assert_not_called()
        injected_sync_api.close.assert_called_once_with()
        server.server_close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
