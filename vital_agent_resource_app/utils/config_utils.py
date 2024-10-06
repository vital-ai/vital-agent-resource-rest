import logging
import yaml


class ConfigUtils:

    @staticmethod
    def load_config():
        with open("app_config.yaml", "r") as config_stream:
            try:
                return yaml.safe_load(config_stream)
            except yaml.YAMLError as exc:
                logger = logging.getLogger("VitalAgentResourceAppLogger")
                logger.info("failed to load config file")
