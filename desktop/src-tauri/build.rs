fn main() {
    assert!(
        std::env::var("PROFILE").as_deref() != Ok("release") || !tauri_build::is_dev(),
        "Release builds must embed the frontend. Use `npm run tauri -- build --no-bundle` \
         or `cargo build --release --features tauri/custom-protocol`."
    );
    // Direct cargo builds must re-embed the current frontend, including renamed
    // Vite asset chunks; otherwise a successful build can ship stale controls.
    println!("cargo:rerun-if-changed=../dist");
    tauri_build::build()
}
