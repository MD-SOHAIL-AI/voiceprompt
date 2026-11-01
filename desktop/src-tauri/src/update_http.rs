//! Small synchronous WinHTTP adapter. OS trust/proxy settings apply; redirects
//! are followed explicitly so HTTPS and the asset-host allowlist cannot widen.
use std::{
    ffi::c_void,
    io, ptr,
    time::{Duration, Instant},
};
use windows_sys::Win32::Networking::WinHttp::*;

struct Handle(*mut c_void);
impl Handle {
    fn new(value: *mut c_void) -> Result<Self, String> {
        if value.is_null() {
            Err("Could not connect to GitHub. Check your connection and retry.".into())
        } else {
            Ok(Self(value))
        }
    }
}
impl Drop for Handle {
    fn drop(&mut self) {
        unsafe {
            WinHttpCloseHandle(self.0);
        }
    }
}

fn wide(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(Some(0)).collect()
}

pub struct Response {
    request: Handle,
    _connection: Handle,
    _session: Handle,
    deadline: Instant,
}

impl Response {
    fn header(&self, kind: u32) -> Option<String> {
        let mut buffer = vec![0_u16; 16384];
        let mut length = (buffer.len() * 2) as u32;
        let ok = unsafe {
            WinHttpQueryHeaders(
                self.request.0,
                kind,
                ptr::null(),
                buffer.as_mut_ptr().cast(),
                &mut length,
                ptr::null_mut(),
            )
        };
        (ok != 0).then(|| {
            String::from_utf16_lossy(&buffer[..length as usize / 2])
                .trim_end_matches('\0')
                .to_string()
        })
    }

    pub fn content_length(&self) -> Option<u64> {
        self.header(WINHTTP_QUERY_CONTENT_LENGTH)?.parse().ok()
    }
}

impl io::Read for Response {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        if Instant::now() >= self.deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "Update connection timed out.",
            ));
        }
        let mut count = 0;
        let ok = unsafe {
            WinHttpReadData(
                self.request.0,
                buffer.as_mut_ptr().cast(),
                buffer.len().min(u32::MAX as usize) as u32,
                &mut count,
            )
        };
        if ok == 0 {
            Err(io::Error::new(
                io::ErrorKind::ConnectionAborted,
                "Update connection was interrupted.",
            ))
        } else {
            Ok(count as usize)
        }
    }
}

pub fn get(address: &str, timeout: Duration) -> Result<Response, String> {
    let url = url::Url::parse(address).map_err(|_| "Invalid update address.")?;
    get_at(url, Instant::now() + timeout)
}

fn get_at(mut url: url::Url, deadline: Instant) -> Result<Response, String> {
    let mut count = 0;
    loop {
        if count >= 6 || Instant::now() >= deadline || !crate::updates::allowed_redirect(&url) {
            return Err("Update redirects exceeded their limit.".into());
        }
        unsafe {
            let session = Handle::new(WinHttpOpen(
                wide(concat!("VoicePrompt/", env!("CARGO_PKG_VERSION"))).as_ptr(),
                WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                ptr::null(),
                ptr::null(),
                0,
            ))?;
            if WinHttpSetTimeouts(session.0, 10000, 10000, 10000, 20000) == 0 {
                return Err("Cannot configure connection timeouts.".into());
            }
            let connection = Handle::new(WinHttpConnect(
                session.0,
                wide(url.host_str().ok_or("Invalid host.")?).as_ptr(),
                443,
                0,
            ))?;
            let resource = if let Some(query) = url.query() {
                format!("{}?{query}", url.path())
            } else {
                url.path().into()
            };
            let request = Handle::new(WinHttpOpenRequest(
                connection.0,
                wide("GET").as_ptr(),
                wide(&resource).as_ptr(),
                ptr::null(),
                ptr::null(),
                ptr::null(),
                WINHTTP_FLAG_SECURE,
            ))?;
            let policy = WINHTTP_OPTION_REDIRECT_POLICY_NEVER;
            if WinHttpSetOption(
                request.0,
                WINHTTP_OPTION_REDIRECT_POLICY,
                (&policy as *const u32).cast(),
                4,
            ) == 0
            {
                return Err("Cannot restrict redirects.".into());
            }
            if WinHttpSendRequest(request.0, ptr::null(), 0, ptr::null(), 0, 0, 0) == 0
                || WinHttpReceiveResponse(request.0, ptr::null_mut()) == 0
            {
                return Err("Could not reach GitHub. Check your connection and retry.".into());
            }
            let response = Response {
                request,
                _connection: connection,
                _session: session,
                deadline,
            };
            let status = response
                .header(WINHTTP_QUERY_STATUS_CODE)
                .and_then(|v| v.parse::<u32>().ok())
                .ok_or("Cannot read GitHub's response.")?;
            if status == 200 {
                return Ok(response);
            }
            if matches!(status, 301 | 302 | 303 | 307 | 308) {
                url = url
                    .join(
                        &response
                            .header(WINHTTP_QUERY_LOCATION)
                            .ok_or("Missing redirect address.")?,
                    )
                    .map_err(|_| "Invalid redirect.")?;
                count += 1;
            } else {
                return Err(if status == 404 {
                    "No update release is published yet. Try again later."
                } else {
                    "GitHub could not provide the update. Please retry later."
                }
                .into());
            }
        }
    }
}
