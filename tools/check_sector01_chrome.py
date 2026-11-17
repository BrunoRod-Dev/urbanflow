"""Exercise Sector 01 in visible Chrome through the DevTools protocol."""

import argparse
import asyncio
import base64
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from threading import Thread
import time
from urllib.request import urlopen

from websockets.asyncio.client import connect

from open_replay_qa import create_server


class Browser:
    def __init__(self, socket):
        self.socket = socket
        self.sequence = 0
        self.errors = []

    async def call(self, method, **params):
        self.sequence += 1
        await self.socket.send(json.dumps({'id': self.sequence, 'method': method, 'params': params}))
        while True:
            response = json.loads(await self.socket.recv())
            if response.get('id') == self.sequence:
                if 'error' in response:
                    raise RuntimeError(response['error'])
                return response.get('result', {})
            if response.get('method') == 'Runtime.exceptionThrown':
                self.errors.append(response['params']['exceptionDetails'].get('text'))

    async def evaluate(self, expression):
        result = await self.call('Runtime.evaluate', expression=expression, awaitPromise=True, returnByValue=True)
        if 'exceptionDetails' in result:
            raise RuntimeError(result['result'].get('description', result['exceptionDetails']))
        return result['result'].get('value')

    async def wait(self, expression, timeout=45):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            if value := await self.evaluate(expression):
                return value
            await asyncio.sleep(.2)
        raise RuntimeError(f'Chrome timeout: {expression}')

    async def screenshot(self, path):
        data = await self.call('Page.captureScreenshot', format='png')
        path.write_bytes(base64.b64decode(data['data']))


async def exercise(browser, url, out, seconds, candidate):
    await browser.call('Runtime.enable')
    await browser.call('Page.enable')
    await browser.call('Performance.enable')
    await browser.call('Page.navigate', url=url)
    await browser.call('Page.bringToFront')
    await browser.wait("""(() => {
      const retry = document.querySelector('#geo-retry');
      if (retry && retry.offsetWidth && !window.retriedMap) {
        window.retriedMap = true;
        retry.click();
      }
      return !!document.querySelector('#replay-qa:not([hidden])') && !!document.querySelector('.maplibregl-canvas');
    })()""", 70)
    await browser.evaluate("""
      window.click = id => document.getElementById(id).click();
      window.value = (id, value, kind = 'change') => {
        const control = document.getElementById(id);
        control.value = value;
        control.dispatchEvent(new Event(kind));
      };
      window.go = t => { document.getElementById('timeline').step = 'any'; value('timeline', t - firstTime, 'input'); };
      window.viewSample = t => {
        go(t);
        const i = getFrameIndex(t);
        const flat = interpolate(i, t);
        return {time: firstTime + currentTime, flat};
      };
      window.record = [];
      const mapDraw = geographicMap.drawVehicles;
      geographicMap.drawVehicles = function(cars, ...args) {
        if (window.capture && !replayViews.active) window.lastMap = {time: firstTime + currentTime, cars};
        return mapDraw.call(this, cars, ...args);
      };
      const oldDraw = replayViews.draw;
      replayViews.draw = function(cars, ...args) {
        const start = performance.now();
        const active = oldDraw.call(this, cars, ...args);
        if (active) record.push({start, duration: performance.now() - start, count: cars.length,
          time: args[1], cars: window.capture ? cars : undefined});
        return active;
      };
    """)
    await browser.evaluate("window.initStart = performance.now(); click('use-3d-view')")
    await browser.wait("replayViews.active && document.visibilityState === 'visible'", 80)
    init = await browser.evaluate("performance.now() - initStart")
    metadata = await browser.evaluate("""(() => {
      const canvas = document.querySelector('#scene-canvas canvas');
      const gl = canvas.getContext('webgl2');
      const ext = gl.getExtension('WEBGL_debug_renderer_info');
      return {visibility: document.visibilityState, userAgent: navigator.userAgent,
        canvas: [canvas.width,canvas.height], gpu: ext && gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
        dpr: devicePixelRatio, threads: navigator.hardwareConcurrency};
    })()""")
    assert metadata['visibility'] == 'visible', metadata
    await browser.evaluate("click('qa-fit'); go(110.75); document.querySelector('#scene-frame').scrollIntoView({block:'center'})")
    await browser.screenshot(out / ('candidata-aerea.png' if candidate else 'original-aerea.png'))
    checks = await browser.evaluate("""(() => {
      window.capture = true;
      const times = [110.5, 110.75, 111, 202, 202.25, 202.5];
      const world = times.map(t => { viewSample(t); return record.at(-1); });
      value('qa-vehicle', String(scenario.vehicleIndex.findIndex(item => item.sumoId === 'mansa-1')));
      go(110.75);
      const followed = document.querySelector('#qa-follow-status').textContent;
      click('camera-street');
      click('camera-zoom-in');
      const street = document.querySelector('#camera-street').getAttribute('aria-pressed');
      const selected = document.querySelector('#qa-vehicle').value;
      const before = currentTime;
      click('use-map-view');
      const flat = times.map(t => { viewSample(t); return lastMap; });
      go(110.75);
      const switchPreserved = selected === document.querySelector('#qa-vehicle').value && before === currentTime;
      click('use-3d-view');
      return {world, flat, followed, street, switchPreserved, selected};
    })()""")
    await browser.wait("replayViews.active")
    assert checks['street'] == 'true' and checks['switchPreserved'] and checks['selected'] != ''
    for world, flat in zip(checks['world'], checks['flat']):
        assert world['time'] == flat['time'] and world['cars'] == flat['cars']
    await browser.screenshot(out / ('candidata-seguimiento.png' if candidate else 'original-seguimiento.png'))
    qa = await browser.evaluate(r"""(() => {
      go(firstTime);
      const absent = document.querySelector('#qa-follow-status').textContent;
      const options = [...document.querySelector('#qa-event').options];
      const withTime = options.find(option => option.value && option.textContent.match(/\d(?:\.\d+)? s$/));
      value('qa-event', withTime.value);
      click('qa-locate');
      const locatedIn3D = replayViews.active;
      const beforeJump = currentTime;
      click('qa-jump');
      const jumped = {time: firstTime + currentTime, moved: beforeJump !== currentTime,
        active: replayViews.active, label: document.querySelector('#qa-detail').textContent};
      click('qa-fit');
      const checkbox = document.querySelector('[data-qa-layer="cars"]');
      checkbox.click();
      const toggledOff = !checkbox.checked;
      checkbox.click();
      document.querySelector('#qa-raw').click();
      const raw = replayQa.raw;
      document.querySelector('#qa-raw').click();
      window.capture = false;
      return {absent, locatedIn3D, jumped, toggledOff, raw};
    })()""")
    assert qa['locatedIn3D'] and qa['jumped']['active'] and qa['jumped']['moved'] and qa['toggledOff'] and qa['raw'], qa
    await browser.evaluate("click('qa-fit'); go(55); value('speed', '1'); click('play')")
    await asyncio.sleep(10)
    await browser.evaluate("""
      record.length = 0;
      window.visibilityChanges = [];
      document.addEventListener('visibilitychange', () => visibilityChanges.push({
        state: document.visibilityState, time: firstTime + currentTime
      }));
    """)
    start = await browser.call('Performance.getMetrics')
    await asyncio.sleep(seconds)
    finish = await browser.call('Performance.getMetrics')
    performance = await browser.evaluate("""(() => {
      click('play');
      const frames = record.slice();
      const stats = values => {
        values.sort((a,b) => a-b);
        return {p50: values[Math.ceil(values.length * .5) - 1], p95: values[Math.ceil(values.length * .95) - 1],
          max: values.at(-1)};
      };
      const intervals = frames.slice(1).map((row, i) => row.start - frames[i].start);
      return {frames: frames.length, intervalsMs: stats(intervals), drawCpuMs: stats(frames.map(row => row.duration)),
        activeVehicles: stats(frames.map(row => row.count)), over250ms: intervals.filter(n => n > 250).length,
        longIntervals: intervals.flatMap((gap, i) => gap > 250 ? [{gap, time: frames[i].time}] : []),
        visibility: document.visibilityState, visibilityChanges, windowMs: frames.at(-1).start - frames[0].start};
    })()""")
    before = {entry['name']: entry['value'] for entry in start['metrics']}
    after = {entry['name']: entry['value'] for entry in finish['metrics']}
    performance['chromeSeconds'] = {name: after[name] - before[name]
                                     for name in ('TaskDuration', 'ScriptDuration', 'LayoutDuration') if name in after}
    return {'initializationMs': init, 'environment': metadata, 'samePoseAndTimeCases': [
        {'time': row['time'], 'vehicles': row['count']} for row in checks['world']],
        'followStatusAtSelection': checks['followed'], 'streetSelected': checks['street'],
        'switchPreserved': checks['switchPreserved'], 'qa': qa, 'performance': performance,
        'runtimeExceptions': browser.errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('qa', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--seconds', type=int, default=62)
    parser.add_argument('--candidate', action='store_true')
    parser.add_argument('--chrome', default=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    args = parser.parse_args()
    replay_id = json.loads(args.manifest.read_bytes())['replayId']
    with create_server(args.manifest.parent, replay_id, args.qa, args.manifest.with_name('sector01.geojson')) as server:
        Thread(target=server.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
            log = args.out / ('chrome-candidata.log' if args.candidate else 'chrome-original.log')
            with log.open('xb') as stream:
                process = subprocess.Popen([args.chrome, f'--user-data-dir={profile}', '--remote-debugging-port=0',
                    '--no-first-run', '--no-default-browser-check', '--window-size=1440,900', 'about:blank'],
                    stdout=stream, stderr=stream)
                try:
                    port_file = Path(profile) / 'DevToolsActivePort'
                    for _ in range(120):
                        if port_file.exists():
                            break
                        time.sleep(.25)
                    port = int(port_file.read_text().splitlines()[0])
                    tabs = json.load(urlopen(f'http://127.0.0.1:{port}/json/list', timeout=8))
                    tab = next(tab for tab in tabs if tab['type'] == 'page')
                    url = f'http://127.0.0.1:{server.server_port}/?qa=1#estudio/{replay_id}'

                    async def run():
                        async with connect(tab['webSocketDebuggerUrl'], max_size=16_000_000) as socket:
                            browser = Browser(socket)
                            try:
                                return await exercise(browser, url, args.out, args.seconds, args.candidate)
                            except Exception:
                                name = 'chrome-error-candidata.png' if args.candidate else 'chrome-error-original.png'
                                await browser.screenshot(args.out / name)
                                print(await browser.evaluate("document.querySelector('#replay-view-feedback')?.textContent"),
                                      file=sys.stderr)
                                raise

                    report = asyncio.run(run())
                    filename = 'chrome-candidata.json' if args.candidate else 'chrome-original.json'
                    with (args.out / filename).open('x', encoding='utf-8') as result:
                        json.dump(report, result, ensure_ascii=False, indent=2)
                finally:
                    process.terminate()
                    process.wait(timeout=10)
        server.shutdown()


if __name__ == '__main__':
    main()
