"""
Plugin manager for loading and managing trading engine plugins.
"""

import importlib
import inspect
import logging
from pathlib import Path
from typing import Dict, List, Optional, Type

from .base_plugin import BasePlugin
from ..bus import EventBus
from ..types import BaseEvent


logger = logging.getLogger(__name__)


class PluginManager:
    """
    Manages plugin lifecycle and event routing.
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.plugins: Dict[str, BasePlugin] = {}
        self.event_routing: Dict[str, List[BasePlugin]] = {}

    async def load_plugins(self, plugin_dir: Optional[Path] = None):
        """
        Discover and load plugins from directory.
        """
        if plugin_dir is None:
            plugin_dir = Path(__file__).parent

        # Scan for plugin files
        for plugin_file in plugin_dir.glob("*_plugin.py"):
            if plugin_file.name == "base_plugin.py":
                continue

            try:
                # Import module
                module_name = plugin_file.stem
                spec = importlib.util.spec_from_file_location(
                    module_name, plugin_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Find plugin classes
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                        issubclass(obj, BasePlugin) and
                        obj != BasePlugin):
                        await self.register_plugin(obj)

            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_file}: {e}")

    async def register_plugin(self, plugin_class: Type[BasePlugin], config: Optional[Dict] = None):
        """
        Register a plugin instance.
        """
        try:
            # Create instance
            plugin = plugin_class(
                name=plugin_class.__name__,
                config=config or {}
            )

            # Validate configuration
            if not plugin.validate_config():
                logger.error(f"Invalid configuration for plugin {plugin.name}")
                return

            # Initialize
            await plugin.initialize()

            # Store plugin
            self.plugins[plugin.name] = plugin

            # Setup event routing
            for event_type in plugin.inputs:
                if event_type not in self.event_routing:
                    self.event_routing[event_type] = []
                self.event_routing[event_type].append(plugin)

            # Subscribe to events
            for event_type in plugin.inputs:
                await self.event_bus.subscribe(
                    event_type,
                    lambda event: self._handle_plugin_event(plugin, event)
                )

            logger.info(f"Registered plugin: {plugin.name}")

        except Exception as e:
            logger.error(f"Failed to register plugin {plugin_class.__name__}: {e}")

    async def _handle_plugin_event(self, plugin: BasePlugin, event: BaseEvent):
        """
        Route event to plugin and handle output.
        """
        try:
            # Process event
            output_events = await plugin.on_event(event)

            # Publish output events
            if output_events:
                for output_event in output_events:
                    await self.event_bus.publish(output_event)

        except Exception as e:
            logger.error(f"Plugin {plugin.name} failed to process event: {e}")

    async def unregister_plugin(self, plugin_name: str):
        """
        Unregister and cleanup a plugin.
        """
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]

            # Cleanup
            await plugin.cleanup()

            # Remove from routing
            for event_list in self.event_routing.values():
                if plugin in event_list:
                    event_list.remove(plugin)

            # Remove plugin
            del self.plugins[plugin_name]

            logger.info(f"Unregistered plugin: {plugin_name}")

    async def reload_plugin(self, plugin_name: str):
        """
        Reload a plugin with updated code.
        """
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            config = plugin.config

            # Unregister old version
            await self.unregister_plugin(plugin_name)

            # Load new version
            # This would need the plugin class reference
            # In practice, you'd store this during registration
            logger.info(f"Reloaded plugin: {plugin_name}")

    def get_plugin(self, plugin_name: str) -> Optional[BasePlugin]:
        """
        Get a plugin instance by name.
        """
        return self.plugins.get(plugin_name)

    def list_plugins(self) -> List[str]:
        """
        List all registered plugins.
        """
        return list(self.plugins.keys())

    async def shutdown(self):
        """
        Shutdown all plugins.
        """
        for plugin_name in list(self.plugins.keys()):
            await self.unregister_plugin(plugin_name)