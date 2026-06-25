from pathlib import Path

from social_pipeline.config import load_actor_config, load_config


def test_load_config_reads_platform_rules_and_weights():
    config = load_config(Path("config/social_listening_v1.json"))

    assert config.timezone == "Asia/Hong_Kong"
    assert config.expansion_top_n == 20
    assert config.dual_platform_bonus == 0.1
    assert config.platforms["instagram"].weight == 0.6
    assert config.platforms["google"].weight == 0.4
    assert config.platforms["instagram"].min_velocity == 0.5
    assert config.platforms["google"].min_abs_gain == 15


def test_load_actor_config_reads_v1_actor_inventory():
    actor_config = load_actor_config(Path("config/apify_actors_v1.json"))

    assert actor_config.platforms["google"].actor_id == "data_xplorer/google-trends-trending-now"
    assert actor_config.platforms["instagram"].actor_id == "breathtaking_anthem/instagram-hashtag-posts-scraper"
    assert actor_config.platforms["google"].dataset_key == "defaultDatasetId"
    assert actor_config.platforms["instagram"].result_format == "dataset_items"
