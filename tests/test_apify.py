# Tests for social_pipeline.apify
#
# The apify module currently exposes one public function:
#   fetch_platform_payloads(actor_config, seed_snapshot, windows, apify_token)
#
# It triggers real Apify actors and returns normalised raw payloads.
# Because it depends on live Apify API calls, unit tests are not practical
# without a mockable runner injection point.
#
# TODO: Add a runner injection seam to fetch_platform_payloads so that
# unit tests can verify request construction and normalisation without
# hitting the Apify API.
