# coding=utf-8
import pytz
from datetime import datetime
from mock import patch
from monitorrent.plugins.trackers import LoginResult, TrackerSettings, CloudflareChallengeSolverSettings
from monitorrent.plugins.trackers.kinozal import KinozalPlugin, KinozalLoginFailedException, KinozalTopic
from monitorrent.plugins.trackers.kinozal import KinozalDateParser
from tests import use_vcr, DbTestCase
from tests.plugins.trackers import TrackerSettingsMock
from tests.plugins.trackers.kinozal.kinozal_helper import KinozalHelper


helper = KinozalHelper()
# helper = KinozalHelper.login('realusername', 'realpassword')


class MockDatetime(datetime):
    mock_now = None

    @classmethod
    def now(cls, tz=None):
        return cls.mock_now


class KinozalPluginTest(DbTestCase):
    def setUp(self):
        super(KinozalPluginTest, self).setUp()
        cloudflare_challenge_solver_settings = CloudflareChallengeSolverSettings(False, 10000, False, False, 0)
        self.tracker_settings = TrackerSettingsMock(10, None, cloudflare_challenge_solver_settings)
        self.plugin = KinozalPlugin()
        self.plugin.init(self.tracker_settings)
        self.urls_to_check = [
            "https://kinozal.tv/details.php?id=1506818"
        ]

    def test_can_parse_url(self):
        for url in self.urls_to_check:
            self.assertTrue(self.plugin.can_parse_url(url))

        bad_urls = [
            "https://kinozal.com/details.php?id=1506818",
            "https://belzal.com/details.php?id=1506818",
        ]
        for url in bad_urls:
            self.assertFalse(self.plugin.can_parse_url(url))

    @use_vcr
    def test_parse_url_success(self):
        parsed_url = self.plugin.parse_url("https://kinozal.tv/details.php?id=1506818")
        assert parsed_url['original_name'] == u'Война против всех / War on Everyone / 2016 / ДБ / WEB-DLRip'

    @use_vcr
    def test_login_verify_fail(self):
        assert not self.plugin.verify()
        assert self.plugin.login() == LoginResult.CredentialsNotSpecified

        credentials = {'username': '', 'password': ''}
        assert self.plugin.update_credentials(credentials) == LoginResult.CredentialsNotSpecified
        assert not self.plugin.verify()

        credentials = {'username': helper.fake_login, 'password': helper.fake_password}
        assert self.plugin.update_credentials(credentials) == LoginResult.IncorrentLoginPassword
        assert not self.plugin.verify()

    @helper.use_vcr
    def test_login_verify_success(self):
        credentials = {'username': helper.real_login, 'password': helper.real_password}
        self.assertEqual(self.plugin.update_credentials(credentials), LoginResult.Ok)
        self.assertTrue(self.plugin.verify())

    def test_login_failed_exceptions_1(self):
        # noinspection PyUnresolvedReferences
        with patch.object(self.plugin.tracker, 'login',
                          side_effect=KinozalLoginFailedException(1, 'Invalid login or password')):
            credentials = {'username': helper.real_login, 'password': helper.real_password}
            self.assertEqual(self.plugin.update_credentials(credentials), LoginResult.IncorrentLoginPassword)

    def test_login_failed_exceptions_173(self):
        # noinspection PyUnresolvedReferences
        with patch.object(self.plugin.tracker, 'login',
                          side_effect=KinozalLoginFailedException(173, 'Invalid login or password')):
            credentials = {'username': helper.real_login, 'password': helper.real_password}
            self.assertEqual(self.plugin.update_credentials(credentials), LoginResult.Unknown)

    def test_login_unexpected_exceptions(self):
        # noinspection PyUnresolvedReferences
        with patch.object(self.plugin.tracker, 'login', side_effect=Exception):
            credentials = {'username': helper.real_login, 'password': helper.real_password}
            self.assertEqual(self.plugin.update_credentials(credentials), LoginResult.Unknown)

    def test_prepare_request(self):
        cookies = {'uid': helper.fake_uid, 'pass': helper.fake_pass}
        # noinspection PyUnresolvedReferences
        with patch.object(self.plugin.tracker, 'get_cookies', result=cookies):
            url = "https://kinozal.tv/details.php?id=1506818"
            request = self.plugin._prepare_request(KinozalTopic(url=url))
            self.assertIsNotNone(request)
            self.assertEqual(request.headers['referer'], url)
            self.assertEqual(request.url, 'https://dl.kinozal.tv/download.php?id=1506818')

    @use_vcr
    def test_get_last_torrent_update_for_updated_yesterday_success(self):
        url = 'https://kinozal.tv/details.php?id=1831370'
        topic = KinozalTopic(id=1, url=url, last_torrent_update=datetime(2021, 3, 17, 10, 10, tzinfo=pytz.utc))
        expected = KinozalDateParser.tz_moscow.localize(datetime(2021, 3, 18, 23, 12)).astimezone(pytz.utc)

        server_now = datetime(2021, 3, 19, 12, 0, 0, tzinfo=pytz.utc)
        MockDatetime.mock_now = server_now

        with patch('monitorrent.plugins.trackers.kinozal.datetime.datetime', MockDatetime):
            assert self.plugin.check_changes(topic)
            assert topic.last_torrent_update == expected

    @use_vcr
    def test_get_last_torrent_update_for_updated_today_success(self):
        url = 'https://kinozal.tv/details.php?id=1496310'
        topic = KinozalTopic(id=1, url=url, last_torrent_update=None)
        expected = KinozalDateParser.tz_moscow.localize(datetime(2017, 1, 20, 1, 30)).astimezone(pytz.utc)

        server_now = datetime(2017, 1, 20, 12, 0, 0, tzinfo=pytz.utc)
        MockDatetime.mock_now = server_now

        with patch('monitorrent.plugins.trackers.kinozal.datetime.datetime', MockDatetime):
            assert self.plugin.check_changes(topic)
            assert topic.last_torrent_update == expected

    @use_vcr
    def test_get_last_torrent_update_for_updated_in_particular_success(self):
        url = 'https://kinozal.tv/details.php?id=1508210'
        topic = KinozalTopic(id=1, url=url, last_torrent_update=datetime(2017, 1, 26, 10, 10, tzinfo=pytz.utc))
        expected = KinozalDateParser.tz_moscow.localize(datetime(2017, 1, 26, 21, 24)).astimezone(pytz.utc)

        assert self.plugin.check_changes(topic)
        assert topic.last_torrent_update == expected

    @use_vcr
    def test_get_last_torrent_update_for_updated_in_particular_not_changed(self):
        url = 'https://kinozal.tv/details.php?id=1508210'
        expected = KinozalDateParser.tz_moscow.localize(datetime(2017, 1, 26, 21, 24)).astimezone(pytz.utc)
        topic = KinozalTopic(id=1, url=url, last_torrent_update=expected)

        assert not self.plugin.check_changes(topic)
        assert topic.last_torrent_update == expected

    @use_vcr
    def test_get_last_torrent_update_without_updates_success(self):
        url = 'https://kinozal.tv/details.php?id=1831382'
        expected = KinozalDateParser.tz_moscow.localize(datetime(2021, 3, 15, 23, 27)).astimezone(pytz.utc)
        topic = KinozalTopic(id=1, url=url, last_torrent_update=None)

        assert self.plugin.check_changes(topic)
        assert topic.last_torrent_update == expected

