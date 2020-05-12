import json
import socket
import logging
import subprocess
from aiohttp import web
from aiohttp_jinja2 import template
from datetime import date

from app.service.auth_svc import check_authorization
from app.utility.base_world import BaseWorld

from plugins.crag.app.crag_svc import CragService


class CragGui(BaseWorld):

    def __init__(self, services, nmap_installed):
        self.services = services
        self.auth_svc = services.get('auth_svc')
        self.file_svc = services.get('file_svc')
        self.nmap_installed = 1 if nmap_installed else 0
        self.crag_svc = CragService(services)
        self.log = logging.getLogger('crag_gui')

    @check_authorization
    @template('crag.html')
    async def splash(self, request):
        return dict(nmap=self.nmap_installed, input_parsers=self.crag_svc.parsers.keys())

    @check_authorization
    async def crag_core(self, request):
        try:
            data = dict(await request.json())
            index = data.pop('index')
            options = dict(
                DELETE=dict(),
                PUT=dict(),
                POST=dict(
                    scan=lambda d: self.scan(),
                    import_scan=lambda d: self.import_report(d)
                )
            )
            if index not in options[request.method]:
                return web.HTTPBadRequest(text='index: %s is not a valid index for the crag plugin' % index)
            return web.json_response(await options[request.method][index](data))
        except Exception as e:
            self.log.error(repr(e), exc_info=True)

    async def scan(self):
        machine_ip = self.get_machine_ip()
        report_name = '%s-%s.xml' % (machine_ip.replace('.', '_'), date.today().strftime("%b-%d-%Y"))
        self.log.debug('scanning %s' % machine_ip)
        command = 'nmap --script plugins/crag/nmap/scripts/nmap-vulners -sV -Pn -oX plugins/crag/data/reports/%s %s/24' % (report_name, machine_ip)
        failcode = subprocess.call(command.split(' '), shell=False)
        if not failcode:
            source = await self.crag_svc.import_scan('nmap', report_name)
            return dict(output='scanned system and generated source: %s' % source)
        return dict(output='failure occurred when scanning system, please check server logs')

    async def import_report(self, data):
        self.log.debug(json.dumps(data))
        scan_type = data.get('format')
        report_name = data.get('filename')
        source = await self.crag_svc.import_scan(scan_type, report_name)
        return dict(output='report process and available as source: %s' % source)

    @check_authorization
    async def store_report(self, request):
        return await self.file_svc.save_multipart_file_upload(request, 'plugins/crag/data/reports')

    @staticmethod
    def get_machine_ip():
        # this gets the exit IP, so if you are on a VPN it will get you the IP on the VPN network and not your local network IP
        def get_ip():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('10.255.255.255', 1))
                ip = s.getsockname()[0]
            except Exception:
                ip = '127.0.0.1'
            finally:
                s.close()
            return ip

        return get_ip()