// X-Agent 桌面壳：把 React web 前端套壳，提供本地后端代理能力。
// 前端主链路仍走浏览器 HTTP/SSE 直连后端（localhost:8000）；
// 此处提供 call_backend_api 命令作为备用（带鉴权转发）。

#[tauri::command]
async fn call_backend_api(
    path: String,
    method: String,
    token: Option<String>,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let url = format!("http://127.0.0.1:8000{}", path);
    let client = reqwest::Client::new();
    let mut req = match method.to_uppercase().as_str() {
        "GET" => client.get(&url),
        "POST" => client.post(&url),
        "PUT" => client.put(&url),
        "DELETE" => client.delete(&url),
        _ => return Err(format!("unsupported method: {method}")),
    };
    if let Some(t) = token {
        req = req.bearer_auth(t);
    }
    if let Some(b) = body {
        req = req.json(&b);
    }
    let resp = req
        .send()
        .await
        .map_err(|e| e.to_string())?;
    let status = resp.status();
    let text = resp.text().await.map_err(|e| e.to_string())?;
    if !status.is_success() {
        return Err(format!("backend {}: {}", status, text));
    }
    serde_json::from_str::<serde_json::Value>(&text)
        .map_err(|e| format!("解析失败: {e}; body: {text}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![call_backend_api])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
