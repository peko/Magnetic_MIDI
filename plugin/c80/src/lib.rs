//! Wooting Analog SDK C-ABI plugin for the CIDOO C80.
//!
//! Exports the functions from the SDK's `includes/plugin.h`. ABI 1 (SDK 0.9.x) by default,
//! ABI 2 (SDK 0.10+, adds `support_level`) with `--features abi2`.
//! Analog value per key = travel / max_travel (0.0..=1.0), keyed by HID usage.
//!
//! Set `CIDOO_PLUGIN_LOG=debug` to get logs on stderr.

mod device;
mod keymap;

use device::State;
use std::ffi::{c_char, c_float, c_int, c_void};
use std::panic::catch_unwind;
use std::sync::atomic::Ordering;
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;

pub use keymap::KEYMAP;

#[no_mangle]
#[used]
pub static ANALOG_SDK_PLUGIN_ABI_VERSION: u32 = if cfg!(feature = "abi2") { 2 } else { 1 };

// --- result codes / enums (wooting-analog-sdk.h) ---
const RESULT_OK: c_int = 1;
const RESULT_UNINITIALIZED: c_int = -2000;
const RESULT_NO_DEVICES: c_int = -1999;
const RESULT_FAILURE: c_int = -1997;
const EVENT_CONNECTED: c_int = 1;
const EVENT_DISCONNECTED: c_int = 2;
const DEVICE_TYPE_KEYBOARD: c_int = 1;

pub type DeviceId = u64;

#[repr(C)]
pub struct DeviceInfoFfi {
    pub vendor_id: u16,
    pub product_id: u16,
    pub manufacturer_name: *const c_char,
    pub device_name: *const c_char,
    pub device_id: DeviceId,
    pub device_type: c_int,
    #[cfg(feature = "abi2")]
    pub support_level: c_int, // 0 = Limited
}

pub type DeviceEventCb = extern "C" fn(*const c_void, c_int, *const DeviceInfoFfi);

struct Plugin {
    state: Arc<State>,
    thread: Option<JoinHandle<()>>,
    /// Boxed so its address is stable for as long as the plugin is loaded.
    info: Arc<Mutex<Box<DeviceInfoFfi>>>,
}

// Raw pointers in DeviceInfoFfi point at 'static C string literals.
unsafe impl Send for DeviceInfoFfi {}

struct Callback {
    data: usize,
    cb: DeviceEventCb,
}

static PLUGIN: Mutex<Option<Plugin>> = Mutex::new(None);
static CALLBACK: Mutex<Option<Callback>> = Mutex::new(None);

const MANUFACTURER: &std::ffi::CStr = c"CIDOO";
const DEVICE_NAME: &std::ffi::CStr = c"CIDOO C80";

/// FNV-1a over vid/pid/name — stable per model (the C80 reports no serial number).
fn device_id(pid: u16) -> DeviceId {
    let mut h: u64 = 0xcbf29ce484222325;
    for b in device::VID.to_le_bytes().into_iter().chain(pid.to_le_bytes()).chain(DEVICE_NAME.to_bytes().iter().copied()) {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

fn hid_to_index(code: u16) -> Option<usize> {
    KEYMAP.iter().find(|(_, h)| *h == code).map(|(i, _)| *i as usize)
}

fn analog(state: &State, idx: usize) -> f32 {
    let max = state.max_travel.load(Ordering::Relaxed).max(1) as f32;
    (state.travel[idx].load(Ordering::Relaxed) as f32 / max).clamp(0.0, 1.0)
}

fn fire(event: c_int, info: *const DeviceInfoFfi) {
    if let Ok(g) = CALLBACK.lock() {
        if let Some(c) = g.as_ref() {
            (c.cb)(c.data as *const c_void, event, info);
        }
    }
}

// ------------------------------- exported ABI -------------------------------

#[no_mangle]
pub extern "C" fn name() -> *const c_char {
    c"CIDOO Hall-effect Plugin".as_ptr()
}

#[no_mangle]
pub extern "C" fn initialise(callback_data: *const c_void, callback: Option<DeviceEventCb>) -> c_int {
    catch_unwind(|| {
        if std::env::var_os("CIDOO_PLUGIN_LOG").is_some() {
            let _ = env_logger::Builder::from_env(env_logger::Env::new().filter("CIDOO_PLUGIN_LOG")).try_init();
        }
        let mut g = PLUGIN.lock().unwrap();
        if g.is_some() {
            return RESULT_OK;
        }
        *CALLBACK.lock().unwrap() = callback.map(|cb| Callback { data: callback_data as usize, cb });

        let state = Arc::new(State::new());
        let info = Arc::new(Mutex::new(Box::new(DeviceInfoFfi {
            vendor_id: device::VID,
            product_id: 0,
            manufacturer_name: MANUFACTURER.as_ptr(),
            device_name: DEVICE_NAME.as_ptr(),
            device_id: 0,
            device_type: DEVICE_TYPE_KEYBOARD,
            #[cfg(feature = "abi2")]
            support_level: 0,
        })));
        let indices: Vec<usize> = KEYMAP.iter().map(|(i, _)| *i as usize).collect();
        let (st, inf) = (state.clone(), info.clone());
        let thread = std::thread::Builder::new()
            .name("cidoo-analog".into())
            .spawn(move || {
                let st2 = st.clone();
                device::run(st, indices, move |connected| {
                    let ptr = {
                        let mut i = inf.lock().unwrap();
                        let pid = st2.pid.load(Ordering::Relaxed);
                        i.product_id = pid;
                        i.device_id = device_id(pid);
                        &**i as *const DeviceInfoFfi
                    };
                    fire(if connected { EVENT_CONNECTED } else { EVENT_DISCONNECTED }, ptr);
                })
            })
            .ok();
        if thread.is_none() {
            return RESULT_FAILURE;
        }
        *g = Some(Plugin { state: state.clone(), thread, info });
        drop(g); // don't hold the lock while waiting: the connect callback may call back into us
        // Give the reader a moment so a plugged-in keyboard is visible right after init.
        for _ in 0..50 {
            if state.connected.load(Ordering::Acquire) {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        RESULT_OK
    })
    .unwrap_or(RESULT_FAILURE)
}

#[no_mangle]
pub extern "C" fn is_initialised() -> bool {
    PLUGIN.lock().map(|g| g.is_some()).unwrap_or(false)
}

#[no_mangle]
pub extern "C" fn unload() {
    let _ = catch_unwind(|| {
        // Drop the SDK callback first: it is invalid after we return.
        *CALLBACK.lock().unwrap() = None;
        let p = PLUGIN.lock().unwrap().take();
        if let Some(mut p) = p {
            p.state.stop.store(true, Ordering::Relaxed);
            if let Some(t) = p.thread.take() {
                let _ = t.join();
            }
        }
    });
}

/// Returns the count written, 0 if nothing is pressed, or an error code.
/// # Safety
/// Pointers must be valid for `len` elements (SDK contract, see plugin.h).
#[no_mangle]
pub unsafe extern "C" fn read_full_buffer(code_buffer: *mut u16, analog_buffer: *mut c_float, len: c_int, device: DeviceId) -> c_int {
    catch_unwind(|| {
        let g = PLUGIN.lock().unwrap();
        let Some(p) = g.as_ref() else { return RESULT_UNINITIALIZED };
        if !p.state.connected.load(Ordering::Acquire) {
            return if device == 0 { 0 } else { RESULT_NO_DEVICES };
        }
        if device != 0 && device != p.info.lock().unwrap().device_id {
            return RESULT_NO_DEVICES;
        }
        if code_buffer.is_null() || analog_buffer.is_null() || len <= 0 {
            return 0;
        }
        let mut n = 0usize;
        for (idx, hid) in KEYMAP.iter() {
            if n >= len as usize {
                break;
            }
            let v = analog(&p.state, *idx as usize);
            if v > 0.0 {
                unsafe {
                    *code_buffer.add(n) = *hid;
                    *analog_buffer.add(n) = v;
                }
                n += 1;
            }
        }
        n as c_int
    })
    .unwrap_or(RESULT_FAILURE)
}

/// # Safety
/// Pointers must be valid for `len` elements (SDK contract, see plugin.h).
#[no_mangle]
pub unsafe extern "C" fn device_info(buffer: *mut *const DeviceInfoFfi, len: c_int) -> c_int {
    catch_unwind(|| {
        let g = PLUGIN.lock().unwrap();
        let Some(p) = g.as_ref() else { return RESULT_UNINITIALIZED };
        if !p.state.connected.load(Ordering::Acquire) || buffer.is_null() || len < 1 {
            return 0;
        }
        let ptr = &**p.info.lock().unwrap() as *const DeviceInfoFfi;
        unsafe { *buffer = ptr };
        1
    })
    .unwrap_or(RESULT_FAILURE)
}

#[no_mangle]
pub extern "C" fn read_analog(code: u16, device: DeviceId) -> c_float {
    catch_unwind(|| {
        let g = PLUGIN.lock().unwrap();
        let Some(p) = g.as_ref() else { return RESULT_UNINITIALIZED as f32 };
        if !p.state.connected.load(Ordering::Acquire) || (device != 0 && device != p.info.lock().unwrap().device_id) {
            return RESULT_NO_DEVICES as f32;
        }
        hid_to_index(code).map(|i| analog(&p.state, i)).unwrap_or(0.0)
    })
    .unwrap_or(RESULT_FAILURE as f32)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keymap_sane() {
        assert_eq!(KEYMAP.len(), 82);
        assert!(KEYMAP.iter().all(|(i, _)| (*i as usize) < device::N_SLOTS));
        assert_eq!(hid_to_index(0x29), Some(0)); // Esc
        assert_eq!(hid_to_index(0x1D), Some(90)); // Z
    }

    #[test]
    fn struct_layout() {
        // Must match the C struct in wooting-analog-sdk.h (x86_64/aarch64).
        assert_eq!(std::mem::offset_of!(DeviceInfoFfi, manufacturer_name), 8);
        assert_eq!(std::mem::offset_of!(DeviceInfoFfi, device_id), 24);
        assert_eq!(std::mem::offset_of!(DeviceInfoFfi, device_type), 32);
        #[cfg(feature = "abi2")]
        assert_eq!(std::mem::offset_of!(DeviceInfoFfi, support_level), 36);
        assert_eq!(std::mem::size_of::<DeviceInfoFfi>(), 40);
    }
}
