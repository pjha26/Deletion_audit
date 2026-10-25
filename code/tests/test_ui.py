"""Local UI boundary checks, without requiring the participant dataset or a browser."""
import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'code'))
from ui import Store, make_handler


class UIEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'work').mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT/'work')
        cls.store = Store(Path(cls.temp.name))
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(cls.store))
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def request(self,path,method='GET',headers=None):
        connection = http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        connection.request(method,path,headers=headers or {})
        response = connection.getresponse()
        status,body,headers = response.status,response.read(),dict(response.getheaders())
        connection.close()
        return status,body,headers

    def test_empty_workspace_shows_no_fabricated_cases(self):
        status,body,_ = self.request('/api/summary')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['cases'],[])

    def test_wrong_host_and_cross_origin_actions_are_rejected(self):
        self.assertEqual(self.request('/api/summary',headers={'Host':'attacker.test'})[0],403)
        self.assertEqual(self.request('/api/run',method='POST')[0],403)
        self.assertEqual(self.request('/api/run',method='POST',headers={'Origin':'https://attacker.test','X-Audit-Local':'1'})[0],403)
        self.assertEqual(self.store.job['state'],'idle')

    def test_unknown_source_cannot_read_arbitrary_files(self):
        self.assertEqual(self.request('/api/source/../../log.txt')[0],404)
        self.assertEqual(self.request('/api/evidence/unknown')[0],404)
        self.assertEqual(self.request('/../log.txt')[0],404)

    def test_assets_are_present_and_script_is_self_hosted(self):
        for path in ('/','/app.js','/styles.css','/favicon.svg'):
            status,body,headers = self.request(path)
            self.assertEqual(status,200,path)
            self.assertGreater(len(body),20)
            self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
            self.assertEqual(headers['X-Content-Type-Options'],'nosniff')


if __name__ == '__main__':
    unittest.main()
