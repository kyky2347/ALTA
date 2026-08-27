/// The current Codex CLI version as embedded at compile time.
pub const CODEX_CLI_VERSION: &str = env!("CARGO_PKG_VERSION");

fn product_name_for_distribution(distribution: Option<&str>) -> &'static str {
    match distribution {
        Some("3.5") => "ALTA v3.5",
        _ => "OpenAI Codex",
    }
}

/// User-facing product name for project-local distributions.
///
/// The exact opt-in keeps upstream Codex branding unchanged when the binary is
/// invoked outside the ALTA launcher or exercised by upstream snapshot tests.
pub(crate) fn product_name() -> &'static str {
    product_name_for_distribution(std::env::var("ALTA_DISTRIBUTION").ok().as_deref())
}

#[cfg(test)]
mod tests {
    use super::product_name_for_distribution;

    #[test]
    fn alta_distribution_uses_alta_product_name() {
        assert_eq!(product_name_for_distribution(Some("3.5")), "ALTA v3.5");
    }

    #[test]
    fn upstream_distribution_keeps_openai_product_name() {
        assert_eq!(product_name_for_distribution(None), "OpenAI Codex");
        assert_eq!(product_name_for_distribution(Some("other")), "OpenAI Codex");
    }
}
