// X-Agent 桌面壳：把 React web 前端套壳，提供本地后端代理能力。
// 前端主链路仍走浏览器 HTTP/SSE 直连后端（localhost:8000）；
// 此处提供 call_backend_api 命令作为备用（带鉴权转发）。

fn parse_method(method: &str) -> Result<reqwest::Method, String> {
    match method.to_ascii_uppercase().as_str() {
        "GET" => Ok(reqwest::Method::GET),
        "POST" => Ok(reqwest::Method::POST),
        "PUT" => Ok(reqwest::Method::PUT),
        "PATCH" => Ok(reqwest::Method::PATCH),
        "DELETE" => Ok(reqwest::Method::DELETE),
        _ => Err(format!("unsupported method: {method}")),
    }
}

fn normalize_backend_base_url(base: &str) -> Result<String, String> {
    let base_url = url::Url::parse(base).map_err(|error| error.to_string())?;
    let host = base_url.host_str().unwrap_or_default();
    if base_url.scheme() != "http"
        || !matches!(host, "127.0.0.1" | "localhost" | "::1")
        || !base_url.username().is_empty()
        || base_url.password().is_some()
        || !matches!(base_url.path(), "" | "/")
        || base_url.query().is_some()
        || base_url.fragment().is_some()
    {
        return Err("backend base URL must be an HTTP loopback origin".to_string());
    }
    Ok(base_url.origin().ascii_serialization())
}

fn configured_backend_base_url() -> Result<String, String> {
    let value = std::env::var("XAGENT_DESKTOP_API_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8000".to_string());
    normalize_backend_base_url(&value)
}

fn build_backend_url(base: &str, path: &str) -> Result<url::Url, String> {
    if !path.starts_with('/')
        || path.starts_with("//")
        || path.contains('\\')
        || path.split('/').any(|part| part == "..")
    {
        return Err("backend path must be an absolute non-escaping path".to_string());
    }
    let normalized_base = normalize_backend_base_url(base)?;
    let mut base_url = url::Url::parse(&normalized_base).map_err(|error| error.to_string())?;
    base_url.set_path(path);
    base_url.set_query(None);
    base_url.set_fragment(None);
    Ok(base_url)
}

#[tauri::command]
fn desktop_api_base_url() -> Result<String, String> {
    configured_backend_base_url()
}

pub async fn diagnose_backend(base: &str) -> Result<serde_json::Value, String> {
    let url = build_backend_url(base, "/health")?;
    let response = reqwest::Client::new()
        .get(url)
        .send()
        .await
        .map_err(|error| error.to_string())?;
    if !response.status().is_success() {
        return Err(format!("backend health returned {}", response.status()));
    }
    response
        .json::<serde_json::Value>()
        .await
        .map_err(|error| format!("backend health JSON parse failed: {error}"))
}

#[tauri::command]
async fn call_backend_api(
    path: String,
    method: String,
    token: Option<String>,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let base = configured_backend_base_url()?;
    let url = build_backend_url(&base, &path)?;
    let client = reqwest::Client::new();
    let mut req = client.request(parse_method(&method)?, url);
    if let Some(t) = token {
        req = req.bearer_auth(t);
    }
    if let Some(b) = body {
        req = req.json(&b);
    }
    let resp = req.send().await.map_err(|e| e.to_string())?;
    let status = resp.status();
    let text = resp.text().await.map_err(|e| e.to_string())?;
    if !status.is_success() {
        return Err(format!("backend returned {status}"));
    }
    serde_json::from_str::<serde_json::Value>(&text)
        .map_err(|e| format!("backend JSON parse failed: {e}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            call_backend_api,
            desktop_api_base_url
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backend_url_accepts_loopback_api_path() {
        let url =
            build_backend_url("http://127.0.0.1:8000", "/api/v1/system/capabilities").unwrap();
        assert_eq!(
            url.as_str(),
            "http://127.0.0.1:8000/api/v1/system/capabilities"
        );
    }

    #[test]
    fn backend_url_rejects_remote_hosts_and_path_escape() {
        assert!(build_backend_url("https://example.com", "/health").is_err());
        assert!(build_backend_url("http://127.0.0.1:8000", "//example.com/steal").is_err());
        assert!(build_backend_url("http://127.0.0.1:8000", "/api/v1/../admin").is_err());
        assert!(build_backend_url("http://127.0.0.1:8000", "health").is_err());
    }

    #[test]
    fn backend_base_url_rejects_remote_credentials_and_paths() {
        assert!(normalize_backend_base_url("http://example.com:8000").is_err());
        assert!(normalize_backend_base_url("http://user@127.0.0.1:8000").is_err());
        assert!(normalize_backend_base_url("http://127.0.0.1:8000/api").is_err());
        assert_eq!(
            normalize_backend_base_url("http://127.0.0.1:8123/").unwrap(),
            "http://127.0.0.1:8123"
        );
    }

    #[test]
    fn request_method_is_allowlisted() {
        assert_eq!(parse_method("get").unwrap(), reqwest::Method::GET);
        assert_eq!(parse_method("DELETE").unwrap(), reqwest::Method::DELETE);
        assert!(parse_method("CONNECT").is_err());
        assert!(parse_method("TRACE").is_err());
    }

    #[tokio::test]
    async fn diagnostics_reports_backend_health() {
        let mut server = mockito::Server::new_async().await;
        let health = server
            .mock("GET", "/health")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"status":"ok","version":"1.1.3"}"#)
            .create_async()
            .await;

        let result = diagnose_backend(&server.url()).await.unwrap();

        assert_eq!(result["status"], "ok");
        assert_eq!(result["version"], "1.1.3");
        health.assert_async().await;
    }
}
