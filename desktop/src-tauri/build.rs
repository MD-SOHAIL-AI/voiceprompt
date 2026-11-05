fn main() {
    // Direct cargo builds must re-embed the current frontend, including renamed
    // Vite asset chunks; otherwise a successful build can ship stale controls.
    println!("cargo:rerun-if-changed=../dist");
    tauri_build::build()
}
