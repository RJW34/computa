"""OBS Scene Collection Builder.

Generates OBS scene collection JSON files with pre-configured
scenes for common streaming scenarios: Gaming, Just Chatting,
Starting Soon, BRB, and Ending screens.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SceneTemplate(Enum):
    """Available scene templates."""

    GAMING = "gaming"
    JUST_CHATTING = "just_chatting"
    STARTING_SOON = "starting_soon"
    BRB = "brb"
    ENDING = "ending"
    FULL_WEBCAM = "full_webcam"


@dataclass
class SourceConfig:
    """Configuration for an OBS source."""

    name: str
    type: str
    settings: dict[str, Any] = field(default_factory=dict)
    # Position and size (relative to 1920x1080 canvas)
    x: int = 0
    y: int = 0
    width: int = 1920
    height: int = 1080
    visible: bool = True
    locked: bool = False


@dataclass
class SceneConfig:
    """Configuration for an OBS scene."""

    name: str
    sources: list[SourceConfig] = field(default_factory=list)


class OBSSceneBuilder:
    """Builds OBS scene collection JSON files.

    Creates scene collections with properly configured sources,
    transforms, and settings for common streaming scenarios.

    Example:
        builder = OBSSceneBuilder("My Stream")
        builder.add_template(SceneTemplate.GAMING)
        builder.add_template(SceneTemplate.JUST_CHATTING)
        builder.add_template(SceneTemplate.BRB)
        builder.export("my_scenes.json")
    """

    def __init__(
        self,
        collection_name: str,
        canvas_width: int = 1920,
        canvas_height: int = 1080,
    ) -> None:
        """Initialize scene builder.

        Args:
            collection_name: Name for the scene collection.
            canvas_width: Canvas width in pixels.
            canvas_height: Canvas height in pixels.
        """
        self.collection_name = collection_name
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.scenes: list[SceneConfig] = []
        self._sources: dict[str, dict[str, Any]] = {}

    def _generate_uuid(self) -> str:
        """Generate a UUID for OBS objects."""
        return str(uuid.uuid4())

    def add_scene(self, scene: SceneConfig) -> None:
        """Add a custom scene to the collection.

        Args:
            scene: SceneConfig object.
        """
        self.scenes.append(scene)

    def add_template(
        self,
        template: SceneTemplate,
        webcam_device: str | None = None,
        alert_url: str | None = None,
        game_name: str | None = None,
    ) -> None:
        """Add a scene from a template.

        Args:
            template: SceneTemplate enum value.
            webcam_device: Optional webcam device name.
            alert_url: Optional StreamElements/Streamlabs alert URL.
            game_name: Optional game name for Game Capture source.
        """
        scene = self._create_scene_from_template(
            template, webcam_device, alert_url, game_name
        )
        self.scenes.append(scene)

    def _create_scene_from_template(
        self,
        template: SceneTemplate,
        webcam_device: str | None,
        alert_url: str | None,
        game_name: str | None,
    ) -> SceneConfig:
        """Create a scene configuration from a template."""
        if template == SceneTemplate.GAMING:
            return self._create_gaming_scene(webcam_device, alert_url, game_name)
        elif template == SceneTemplate.JUST_CHATTING:
            return self._create_just_chatting_scene(webcam_device, alert_url)
        elif template == SceneTemplate.STARTING_SOON:
            return self._create_starting_soon_scene()
        elif template == SceneTemplate.BRB:
            return self._create_brb_scene()
        elif template == SceneTemplate.ENDING:
            return self._create_ending_scene()
        elif template == SceneTemplate.FULL_WEBCAM:
            return self._create_full_webcam_scene(webcam_device, alert_url)
        else:
            raise ValueError(f"Unknown template: {template}")

    def _create_gaming_scene(
        self,
        webcam_device: str | None,
        alert_url: str | None,
        game_name: str | None,
    ) -> SceneConfig:
        """Create a gaming scene with game capture, webcam, and alerts."""
        sources: list[SourceConfig] = []

        # Game Capture (full screen)
        sources.append(SourceConfig(
            name="Game Capture",
            type="game_capture",
            settings={
                "capture_mode": "any_fullscreen",
                "window": game_name or "",
                "capture_cursor": True,
                "anti_cheat_hook": True,
                "allow_transparency": False,
            },
            x=0,
            y=0,
            width=self.canvas_width,
            height=self.canvas_height,
        ))

        # Webcam (bottom right corner)
        if webcam_device:
            webcam_width = 320
            webcam_height = 240
            sources.append(SourceConfig(
                name="Webcam",
                type="dshow_input",
                settings={
                    "video_device_id": webcam_device,
                    "res_type": 1,
                    "resolution": "1920x1080",
                },
                x=self.canvas_width - webcam_width - 20,
                y=self.canvas_height - webcam_height - 20,
                width=webcam_width,
                height=webcam_height,
            ))

        # Alert Box (browser source)
        if alert_url:
            sources.append(SourceConfig(
                name="Alerts",
                type="browser_source",
                settings={
                    "url": alert_url,
                    "width": 800,
                    "height": 600,
                    "css": "",
                    "shutdown": True,
                    "restart_when_active": False,
                },
                x=(self.canvas_width - 800) // 2,
                y=100,
                width=800,
                height=600,
            ))

        return SceneConfig(name="Gaming", sources=sources)

    def _create_just_chatting_scene(
        self,
        webcam_device: str | None,
        alert_url: str | None,
    ) -> SceneConfig:
        """Create a Just Chatting scene with large webcam."""
        sources: list[SourceConfig] = []

        # Background color
        sources.append(SourceConfig(
            name="Background",
            type="color_source",
            settings={
                "color": 0xFF1A1A2E,  # Dark purple-blue
                "width": self.canvas_width,
                "height": self.canvas_height,
            },
            x=0,
            y=0,
            width=self.canvas_width,
            height=self.canvas_height,
        ))

        # Large centered webcam
        if webcam_device:
            webcam_width = 1280
            webcam_height = 720
            sources.append(SourceConfig(
                name="Webcam",
                type="dshow_input",
                settings={
                    "video_device_id": webcam_device,
                    "res_type": 1,
                    "resolution": "1920x1080",
                },
                x=(self.canvas_width - webcam_width) // 2,
                y=(self.canvas_height - webcam_height) // 2 - 50,
                width=webcam_width,
                height=webcam_height,
            ))

        # Alert Box
        if alert_url:
            sources.append(SourceConfig(
                name="Alerts",
                type="browser_source",
                settings={
                    "url": alert_url,
                    "width": 800,
                    "height": 400,
                    "css": "",
                    "shutdown": True,
                },
                x=(self.canvas_width - 800) // 2,
                y=50,
                width=800,
                height=400,
            ))

        # Chat widget placeholder text
        sources.append(SourceConfig(
            name="Chat Label",
            type="text_gdiplus",
            settings={
                "text": "Add your chat widget here",
                "font": {
                    "face": "Arial",
                    "size": 24,
                    "style": "regular",
                },
                "color": 0xFFFFFFFF,
                "opacity": 100,
            },
            x=20,
            y=self.canvas_height - 60,
            width=400,
            height=40,
        ))

        return SceneConfig(name="Just Chatting", sources=sources)

    def _create_starting_soon_scene(self) -> SceneConfig:
        """Create a Starting Soon scene with countdown placeholder."""
        sources: list[SourceConfig] = []

        # Background
        sources.append(SourceConfig(
            name="Background",
            type="color_source",
            settings={
                "color": 0xFF0F0F23,  # Dark blue
                "width": self.canvas_width,
                "height": self.canvas_height,
            },
            x=0,
            y=0,
            width=self.canvas_width,
            height=self.canvas_height,
        ))

        # Starting Soon text
        sources.append(SourceConfig(
            name="Starting Soon Text",
            type="text_gdiplus",
            settings={
                "text": "STARTING SOON",
                "font": {
                    "face": "Arial",
                    "size": 72,
                    "style": "bold",
                },
                "color": 0xFFFFFFFF,
                "opacity": 100,
                "align": "center",
            },
            x=(self.canvas_width - 600) // 2,
            y=(self.canvas_height - 100) // 2 - 100,
            width=600,
            height=100,
        ))

        # Countdown placeholder
        sources.append(SourceConfig(
            name="Countdown Placeholder",
            type="text_gdiplus",
            settings={
                "text": "Add countdown widget here",
                "font": {
                    "face": "Arial",
                    "size": 36,
                    "style": "regular",
                },
                "color": 0xFF888888,
                "opacity": 100,
                "align": "center",
            },
            x=(self.canvas_width - 400) // 2,
            y=(self.canvas_height - 50) // 2 + 50,
            width=400,
            height=50,
        ))

        # Social handles placeholder
        sources.append(SourceConfig(
            name="Social Links",
            type="text_gdiplus",
            settings={
                "text": "@yourusername",
                "font": {
                    "face": "Arial",
                    "size": 28,
                    "style": "regular",
                },
                "color": 0xFFAAAAAA,
                "opacity": 100,
                "align": "center",
            },
            x=(self.canvas_width - 300) // 2,
            y=self.canvas_height - 100,
            width=300,
            height=40,
        ))

        return SceneConfig(name="Starting Soon", sources=sources)

    def _create_brb_scene(self) -> SceneConfig:
        """Create a Be Right Back scene."""
        sources: list[SourceConfig] = []

        # Background
        sources.append(SourceConfig(
            name="Background",
            type="color_source",
            settings={
                "color": 0xFF1A1A2E,
                "width": self.canvas_width,
                "height": self.canvas_height,
            },
            x=0,
            y=0,
            width=self.canvas_width,
            height=self.canvas_height,
        ))

        # BRB text
        sources.append(SourceConfig(
            name="BRB Text",
            type="text_gdiplus",
            settings={
                "text": "BE RIGHT BACK",
                "font": {
                    "face": "Arial",
                    "size": 72,
                    "style": "bold",
                },
                "color": 0xFFFFFFFF,
                "opacity": 100,
                "align": "center",
            },
            x=(self.canvas_width - 700) // 2,
            y=(self.canvas_height - 100) // 2,
            width=700,
            height=100,
        ))

        return SceneConfig(name="Be Right Back", sources=sources)

    def _create_ending_scene(self) -> SceneConfig:
        """Create an ending/raid scene."""
        sources: list[SourceConfig] = []

        # Background
        sources.append(SourceConfig(
            name="Background",
            type="color_source",
            settings={
                "color": 0xFF0F0F23,
                "width": self.canvas_width,
                "height": self.canvas_height,
            },
            x=0,
            y=0,
            width=self.canvas_width,
            height=self.canvas_height,
        ))

        # Thanks for watching text
        sources.append(SourceConfig(
            name="Ending Text",
            type="text_gdiplus",
            settings={
                "text": "THANKS FOR WATCHING!",
                "font": {
                    "face": "Arial",
                    "size": 64,
                    "style": "bold",
                },
                "color": 0xFFFFFFFF,
                "opacity": 100,
                "align": "center",
            },
            x=(self.canvas_width - 800) // 2,
            y=(self.canvas_height - 100) // 2 - 80,
            width=800,
            height=100,
        ))

        # Follow reminder
        sources.append(SourceConfig(
            name="Follow Text",
            type="text_gdiplus",
            settings={
                "text": "Follow for more streams!",
                "font": {
                    "face": "Arial",
                    "size": 32,
                    "style": "regular",
                },
                "color": 0xFFAAAAAA,
                "opacity": 100,
                "align": "center",
            },
            x=(self.canvas_width - 500) // 2,
            y=(self.canvas_height - 50) // 2 + 50,
            width=500,
            height=50,
        ))

        # Social handles
        sources.append(SourceConfig(
            name="Social Links",
            type="text_gdiplus",
            settings={
                "text": "@yourusername everywhere",
                "font": {
                    "face": "Arial",
                    "size": 24,
                    "style": "regular",
                },
                "color": 0xFF888888,
                "opacity": 100,
                "align": "center",
            },
            x=(self.canvas_width - 400) // 2,
            y=self.canvas_height - 80,
            width=400,
            height=30,
        ))

        return SceneConfig(name="Ending", sources=sources)

    def _create_full_webcam_scene(
        self,
        webcam_device: str | None,
        alert_url: str | None,
    ) -> SceneConfig:
        """Create a full-screen webcam scene."""
        sources: list[SourceConfig] = []

        # Full screen webcam
        if webcam_device:
            sources.append(SourceConfig(
                name="Webcam",
                type="dshow_input",
                settings={
                    "video_device_id": webcam_device,
                    "res_type": 1,
                    "resolution": "1920x1080",
                },
                x=0,
                y=0,
                width=self.canvas_width,
                height=self.canvas_height,
            ))

        # Alert Box
        if alert_url:
            sources.append(SourceConfig(
                name="Alerts",
                type="browser_source",
                settings={
                    "url": alert_url,
                    "width": 800,
                    "height": 600,
                    "css": "",
                    "shutdown": True,
                },
                x=(self.canvas_width - 800) // 2,
                y=100,
                width=800,
                height=600,
            ))

        return SceneConfig(name="Full Webcam", sources=sources)

    def _build_source_item(
        self,
        source: SourceConfig,
        source_uuid: str,
    ) -> dict[str, Any]:
        """Build a source item for the scene collection."""
        # Calculate scale based on desired size vs source size
        # For simplicity, we store the transform values
        return {
            "name": source.name,
            "source_uuid": source_uuid,
            "visible": source.visible,
            "locked": source.locked,
            "pos": {
                "x": float(source.x),
                "y": float(source.y),
            },
            "bounds": {
                "x": float(source.width),
                "y": float(source.height),
            },
            "bounds_type": 2,  # Scale to bounds
            "bounds_align": 0,
        }

    def _build_source_definition(self, source: SourceConfig, source_uuid: str) -> dict[str, Any]:
        """Build a source definition for the sources list."""
        return {
            "name": source.name,
            "uuid": source_uuid,
            "id": source.type,
            "versioned_id": f"{source.type}_v2",
            "settings": source.settings,
            "mixers": 255,
            "sync": 0,
            "flags": 0,
            "volume": 1.0,
            "balance": 0.5,
            "enabled": True,
            "muted": False,
            "push-to-mute": False,
            "push-to-mute-delay": 0,
            "push-to-talk": False,
            "push-to-talk-delay": 0,
            "private_settings": {},
        }

    def build(self) -> dict[str, Any]:
        """Build the complete scene collection JSON.

        Returns:
            Dictionary representing the OBS scene collection.
        """
        scene_collection: dict[str, Any] = {
            "name": self.collection_name,
            "uuid": self._generate_uuid(),
            "current_scene": self.scenes[0].name if self.scenes else "",
            "current_program_scene": self.scenes[0].name if self.scenes else "",
            "scene_order": [],
            "groups": [],
            "sources": [],
        }

        # Build scenes and collect sources
        all_sources: dict[str, SourceConfig] = {}
        source_uuid_map: dict[str, str] = {}

        for scene in self.scenes:
            scene_uuid = self._generate_uuid()

            # Add scene to scene_order
            scene_collection["scene_order"].append({
                "name": scene.name,
                "uuid": scene_uuid,
            })

            # Build scene source
            scene_source = {
                "name": scene.name,
                "uuid": scene_uuid,
                "id": "scene",
                "versioned_id": "scene",
                "settings": {
                    "items": [],
                },
                "mixers": 0,
                "sync": 0,
                "flags": 0,
                "volume": 1.0,
                "balance": 0.5,
                "enabled": True,
                "muted": False,
                "private_settings": {},
            }

            # Add sources to scene
            for source in scene.sources:
                # Track unique sources and stable UUIDs
                if source.name not in all_sources:
                    all_sources[source.name] = source
                    source_uuid_map[source.name] = self._generate_uuid()

                # Add source item to scene with the stable UUID
                scene_source["settings"]["items"].append(
                    self._build_source_item(source, source_uuid_map[source.name])
                )

            scene_collection["sources"].append(scene_source)

        # Add all unique sources
        for source in all_sources.values():
            scene_collection["sources"].append(
                self._build_source_definition(source, source_uuid_map[source.name])
            )

        return scene_collection

    def export(self, output_path: Path | str) -> Path:
        """Export scene collection to JSON file.

        Args:
            output_path: Path for the output JSON file.

        Returns:
            Path to the exported file.
        """
        output_path = Path(output_path)
        collection = self.build()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(collection, f, indent=2)

        logger.info(f"Exported scene collection to {output_path}")
        return output_path

    def export_to_obs(self) -> Path | None:
        """Export scene collection directly to OBS scene collections folder.

        Returns:
            Path to the exported file, or None if OBS not found.
        """
        import os

        appdata = os.environ.get("APPDATA")
        if not appdata:
            logger.error("APPDATA environment variable not found")
            return None

        obs_path = Path(appdata) / "obs-studio" / "basic" / "scenes"
        if not obs_path.exists():
            logger.error(f"OBS scenes folder not found: {obs_path}")
            return None

        # Sanitize collection name for filename
        safe_name = "".join(c for c in self.collection_name if c.isalnum() or c in " -_")
        output_path = obs_path / f"{safe_name}.json"

        return self.export(output_path)


def create_streaming_scene_collection(
    collection_name: str = "ABSO Streaming",
    webcam_device: str | None = None,
    alert_url: str | None = None,
) -> OBSSceneBuilder:
    """Create a complete streaming scene collection.

    Convenience function that creates a scene collection with all
    standard streaming scenes configured.

    Args:
        collection_name: Name for the scene collection.
        webcam_device: Webcam device ID (optional).
        alert_url: StreamElements/Streamlabs alert URL (optional).

    Returns:
        Configured OBSSceneBuilder instance.
    """
    builder = OBSSceneBuilder(collection_name)

    builder.add_template(SceneTemplate.STARTING_SOON)
    builder.add_template(SceneTemplate.GAMING, webcam_device, alert_url)
    builder.add_template(SceneTemplate.JUST_CHATTING, webcam_device, alert_url)
    builder.add_template(SceneTemplate.BRB)
    builder.add_template(SceneTemplate.ENDING)

    return builder
