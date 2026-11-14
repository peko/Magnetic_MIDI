//! CIDOO vendor protocol (usage page 0xFF1B, report id 1, 63-byte payload) — just what the
//! plugin needs: identify, trigger config and the live travel stream ("trigger test").
//! See docs/protocol.md.

use hidapi::{HidApi, HidDevice};
use log::{debug, info, warn};
use std::sync::atomic::{AtomicBool, AtomicU16, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

pub const VID: u16 = 0x2E3C;
pub const PIDS: std::ops::RangeInclusive<u16> = 0xC365..=0xC368;
pub const USAGE_PAGE: u16 = 0xFF1B;
pub const N_COLS: usize = 22;
pub const N_SLOTS: usize = 6 * N_COLS;
const PAYLOAD: usize = 63;
const REPORT_ID: u8 = 1;
const HEARTBEAT: Duration = Duration::from_secs(2);
const RETRY: Duration = Duration::from_millis(1000);

/// Shared between the reader thread and the FFI side.
pub struct State {
    pub travel: [AtomicU16; N_SLOTS],
    pub max_travel: AtomicU16,
    pub connected: AtomicBool,
    pub pid: AtomicU16,
    pub stop: AtomicBool,
}

impl State {
    pub fn new() -> Self {
        State {
            travel: std::array::from_fn(|_| AtomicU16::new(0)),
            max_travel: AtomicU16::new(340),
            connected: AtomicBool::new(false),
            pid: AtomicU16::new(0),
            stop: AtomicBool::new(false),
        }
    }

    fn clear(&self) {
        for t in &self.travel {
            t.store(0, Ordering::Relaxed);
        }
    }
}

fn packet(cmd: u8, len: u8, data: &[u8]) -> [u8; PAYLOAD + 1] {
    let mut p = [0u8; PAYLOAD + 1];
    p[0] = REPORT_ID;
    p[1] = cmd;
    p[5] = len;
    p[6..6 + data.len()].copy_from_slice(data);
    p
}

fn open_stream_packet(indices: impl Iterator<Item = usize>) -> [u8; PAYLOAD + 1] {
    let mut d = [0u8; 1 + N_COLS];
    d[0] = 0x02;
    for i in indices {
        d[1 + i % N_COLS] |= 1 << (i / N_COLS);
    }
    packet(0x21, 24, &d)
}

/// Read one payload (report id stripped). Ok(None) on timeout.
fn recv(dev: &HidDevice, timeout_ms: i32) -> hidapi::HidResult<Option<[u8; PAYLOAD]>> {
    let mut buf = [0u8; PAYLOAD + 1];
    let n = dev.read_timeout(&mut buf, timeout_ms)?;
    if n == 0 {
        return Ok(None);
    }
    let mut out = [0u8; PAYLOAD];
    // hidraw delivers the report id as the first byte for numbered reports.
    if buf[0] == REPORT_ID && n == PAYLOAD + 1 {
        out.copy_from_slice(&buf[1..]);
    } else {
        let m = n.min(PAYLOAD);
        out[..m].copy_from_slice(&buf[..m]);
    }
    Ok(Some(out))
}

fn find(api: &mut HidApi) -> Option<(std::ffi::CString, u16)> {
    let _ = api.refresh_devices();
    api.device_list()
        .find(|d| d.vendor_id() == VID && PIDS.contains(&d.product_id()) && d.usage_page() == USAGE_PAGE)
        .map(|d| (d.path().to_owned(), d.product_id()))
}

fn read_max_travel(dev: &HidDevice) -> Option<u16> {
    dev.write(&packet(0x21, 24, &[0x04])).ok()?;
    let deadline = Instant::now() + Duration::from_millis(500);
    while Instant::now() < deadline {
        if let Ok(Some(p)) = recv(dev, 100) {
            if p[0] == 0x21 && p[5] == 0x04 {
                let max = (p[9] as u16) << 8 | p[6] as u16;
                return (max > 0).then_some(max);
            }
        }
    }
    None
}

/// Reader thread body. `on_change(connected)` is called on connect/disconnect.
pub fn run(state: Arc<State>, indices: Vec<usize>, on_change: impl Fn(bool)) {
    let mut api = match HidApi::new() {
        Ok(a) => a,
        Err(e) => {
            warn!("hidapi init failed: {e}");
            return;
        }
    };
    while !state.stop.load(Ordering::Relaxed) {
        let Some((path, pid)) = find(&mut api) else {
            sleep_unless_stopped(&state, RETRY);
            continue;
        };
        let dev = match api.open_path(&path) {
            Ok(d) => d,
            Err(e) => {
                debug!("open {path:?} failed: {e}");
                sleep_unless_stopped(&state, RETRY);
                continue;
            }
        };
        // drain stale input
        while let Ok(Some(_)) = recv(&dev, 10) {}
        if let Some(max) = read_max_travel(&dev) {
            state.max_travel.store(max, Ordering::Relaxed);
        }
        if dev.write(&open_stream_packet(indices.iter().copied())).is_err() {
            sleep_unless_stopped(&state, RETRY);
            continue;
        }
        state.clear();
        state.pid.store(pid, Ordering::Relaxed);
        state.connected.store(true, Ordering::Release);
        info!("CIDOO 0x{pid:04X} connected, max travel {}", state.max_travel.load(Ordering::Relaxed));
        on_change(true);

        let mut last_hb = Instant::now();
        let result: hidapi::HidResult<()> = (|| {
            while !state.stop.load(Ordering::Relaxed) {
                if last_hb.elapsed() >= HEARTBEAT {
                    dev.write(&packet(0x01, 0, &[]))?;
                    last_hb = Instant::now();
                }
                if let Some(p) = recv(&dev, 50)? {
                    if p[0] == 0x21 && p[5] == 0x01 {
                        let idx = p[6] as usize * N_COLS + p[7] as usize;
                        if idx < N_SLOTS {
                            state.travel[idx].store((p[9] as u16) << 8 | p[8] as u16, Ordering::Relaxed);
                        }
                    }
                }
            }
            Ok(())
        })();
        if let Err(e) = &result {
            warn!("device I/O error: {e}");
        } else {
            let _ = dev.write(&packet(0x21, 24, &[0x03])); // close trigger test
        }
        state.connected.store(false, Ordering::Release);
        state.clear();
        on_change(false);
    }
}

fn sleep_unless_stopped(state: &State, d: Duration) {
    let end = Instant::now() + d;
    while Instant::now() < end && !state.stop.load(Ordering::Relaxed) {
        std::thread::sleep(Duration::from_millis(50));
    }
}
