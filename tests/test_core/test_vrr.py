"""Tests for VRR optimization knowledge base."""

from __future__ import annotations

import pytest

from abso.core.vrr import (
    VRR_FPS_CAPS,
    VRR_FPS_CAPS_REFLEX,
    FrameLimiterType,
    GraphicsAPI,
    get_best_ingame_preset,
    get_fighting_game_config,
    get_high_refresh_benefit,
    get_limiter_recommendation,
    get_llm_recommendation,
    get_vrr_fps_cap,
)


class TestVRRFPSCap:
    """Tests for VRR FPS cap calculations."""

    def test_get_vrr_fps_cap_low_refresh_uses_minus_three(self):
        """For refresh < 200Hz, the legacy refresh-3 rule still applies."""
        assert get_vrr_fps_cap(60) == 57
        assert get_vrr_fps_cap(120) == 117
        assert get_vrr_fps_cap(144) == 141
        assert get_vrr_fps_cap(165) == 162

    def test_get_vrr_fps_cap_high_refresh_uses_scaled_margin(self):
        """For 200Hz+ non-Reflex paths, margin scales (Blur Busters 2026).

        At high refresh the legacy -3 rule is too tight for non-Reflex games;
        frame-time variance can briefly hit the ceiling. Modern guidance uses
        3-5% margin so VRR stays engaged.
        """
        assert get_vrr_fps_cap(240) == 233  # was 237, now refresh * 0.97
        assert get_vrr_fps_cap(280) == 272  # was 277, now refresh * 0.97
        assert get_vrr_fps_cap(300) == 285  # was 297, now refresh * 0.95
        assert get_vrr_fps_cap(360) == 342  # was 357, now refresh * 0.95
        assert get_vrr_fps_cap(480) == 456  # was 477, now refresh * 0.95

    def test_get_vrr_fps_cap_reflex_active_uses_minus_three_across_range(self):
        """Reflex-active paths use refresh - 3 even at high refresh.

        With NVIDIA Reflex in the render loop, the engine's dynamic cap is the
        latency control. The static cap is only the V-SYNC safety boundary, so
        the 3-fps headroom is sufficient.
        """
        assert get_vrr_fps_cap(60, reflex_active=True) == 57
        assert get_vrr_fps_cap(144, reflex_active=True) == 141
        assert get_vrr_fps_cap(240, reflex_active=True) == 237
        assert get_vrr_fps_cap(300, reflex_active=True) == 297
        assert get_vrr_fps_cap(360, reflex_active=True) == 357
        assert get_vrr_fps_cap(480, reflex_active=True) == 477

    def test_get_vrr_fps_cap_reflex_fallback_for_unlisted_rates(self):
        """Non-preset refresh rates fall through to refresh - 3 on Reflex paths."""
        assert get_vrr_fps_cap(220, reflex_active=True) == 217
        assert get_vrr_fps_cap(330, reflex_active=True) == 327
        assert get_vrr_fps_cap(540, reflex_active=True) == 537

    def test_get_vrr_fps_cap_fallback_calculation(self):
        """Non-preset values fall through to the scaled formula (non-Reflex)."""
        # Below 200Hz still uses refresh - 3
        assert get_vrr_fps_cap(85) == 82
        assert get_vrr_fps_cap(155) == 152
        # 200-300Hz range falls back to 0.97 scaling for non-preset rates
        assert get_vrr_fps_cap(220) == round(220 * 0.97)  # 213
        assert get_vrr_fps_cap(250) == round(250 * 0.97)  # 243
        # 300Hz+ range falls back to 0.95 scaling
        assert get_vrr_fps_cap(320) == round(320 * 0.95)  # 304
        assert get_vrr_fps_cap(540) == round(540 * 0.95)  # 513

    def test_get_vrr_fps_cap_reflex_default_is_off(self):
        """Default behavior (no reflex_active arg) is the conservative cap."""
        # Identical results without the kwarg confirms backwards compat.
        assert get_vrr_fps_cap(300) == 285
        assert get_vrr_fps_cap(300, reflex_active=False) == 285

    def test_vrr_fps_caps_dict_has_common_values(self):
        """Test that VRR_FPS_CAPS contains expected presets."""
        assert 60 in VRR_FPS_CAPS
        assert 144 in VRR_FPS_CAPS
        assert 240 in VRR_FPS_CAPS
        assert 360 in VRR_FPS_CAPS

    def test_vrr_fps_caps_reflex_dict_has_common_values(self):
        """VRR_FPS_CAPS_REFLEX mirrors the conservative table at same refresh rates."""
        assert VRR_FPS_CAPS_REFLEX[300] == 297
        assert VRR_FPS_CAPS_REFLEX[240] == 237
        # Sub-200 values match the conservative table (refresh - 3 in both).
        assert VRR_FPS_CAPS_REFLEX[144] == VRR_FPS_CAPS[144] == 141


class TestBestInGamePreset:
    """Tests for in-game FPS preset selection."""

    def test_get_best_ingame_preset_exact_match(self):
        """Test when refresh rate matches a preset exactly."""
        # 144Hz monitor, 141 is the VRR target, 120 is the best preset.
        assert get_best_ingame_preset(144) == 120  # 141 target, presets are 60,120,144

    def test_get_best_ingame_preset_custom_presets(self):
        """Test with custom game presets."""
        # Rivals 2 presets
        rivals_presets = [60, 120, 144, 165, 240]

        # 300Hz monitor -> 285 target -> 240 is best preset
        assert get_best_ingame_preset(300, rivals_presets) == 240

        # 165Hz monitor -> 162 target -> 144 is best preset
        assert get_best_ingame_preset(165, rivals_presets) == 144

    def test_get_best_ingame_preset_no_valid_preset(self):
        """Test when no preset is below the VRR target."""
        # If minimum preset is 60 and refresh is 50Hz
        assert get_best_ingame_preset(50, [60, 120]) is None


class TestLimiterRecommendation:
    """Tests for frame limiter recommendations."""

    def test_ingame_custom_values_preferred(self):
        """Test in-game limiter with custom values is recommended."""
        result = get_limiter_recommendation(
            has_ingame_limiter=True,
            ingame_allows_custom=True,
            has_reflex=False,
            refresh_rate=144,
        )
        assert result["limiter"] == FrameLimiterType.IN_GAME
        assert result["fps_cap"] == 141

    def test_ingame_preset_when_close_to_vrr_target(self):
        """Test in-game preset used when within 10 FPS of the VRR target."""
        result = get_limiter_recommendation(
            has_ingame_limiter=True,
            ingame_allows_custom=False,
            has_reflex=False,
            refresh_rate=144,
            available_presets=[60, 120, 135, 144],  # 135 is within 10 of 141
        )
        # 141 is the target, 135 is within 10 of that (141-135=6)
        assert result["limiter"] == FrameLimiterType.IN_GAME
        assert result["fps_cap"] == 135

    def test_rtss_when_preset_too_far(self):
        """Test RTSS recommended when in-game presets are too far from the VRR target."""
        result = get_limiter_recommendation(
            has_ingame_limiter=True,
            ingame_allows_custom=False,
            has_reflex=False,
            refresh_rate=300,
            available_presets=[60, 120],  # 120 is far from 285 (new 300Hz cap)
        )
        assert result["limiter"] == FrameLimiterType.RTSS
        assert result["fps_cap"] == 285  # 300Hz cap updated 2026-05 (was 297)

    def test_reflex_when_no_ingame_limiter(self):
        """Test Reflex recommended when no in-game limiter but Reflex available."""
        result = get_limiter_recommendation(
            has_ingame_limiter=False,
            ingame_allows_custom=False,
            has_reflex=True,
            refresh_rate=144,
        )
        assert result["limiter"] == FrameLimiterType.REFLEX
        assert result["fps_cap"] is None  # Reflex auto-caps

    def test_rtss_fallback(self):
        """Test RTSS as fallback when no in-game limiter or Reflex."""
        result = get_limiter_recommendation(
            has_ingame_limiter=False,
            ingame_allows_custom=False,
            has_reflex=False,
            refresh_rate=144,
        )
        assert result["limiter"] == FrameLimiterType.RTSS
        assert result["fps_cap"] == 141


class TestLLMRecommendation:
    """Tests for Low Latency Mode recommendations."""

    def test_llm_supported_in_dx11(self):
        """Test LLM is recommended for DX11."""
        result = get_llm_recommendation(GraphicsAPI.DX11, has_reflex=False)
        assert result["low_latency_mode"] == "on"

    def test_llm_supported_in_dx9(self):
        """Test LLM is recommended for DX9."""
        result = get_llm_recommendation(GraphicsAPI.DX9, has_reflex=False)
        assert result["low_latency_mode"] == "on"

    def test_reflex_preferred_for_dx12(self):
        """Test Reflex is preferred over LLM for DX12."""
        result = get_llm_recommendation(GraphicsAPI.DX12, has_reflex=True)
        assert result["low_latency_mode"] == "off"
        assert result.get("use_reflex") is True

    def test_reflex_preferred_for_dx11(self):
        """Test Reflex is preferred over driver LLM for DX11 games that support it."""
        result = get_llm_recommendation(GraphicsAPI.DX11, has_reflex=True)
        assert result["low_latency_mode"] == "off"
        assert result.get("use_reflex") is True

    def test_reflex_preferred_for_vulkan(self):
        """Test Reflex is preferred over LLM for Vulkan."""
        result = get_llm_recommendation(GraphicsAPI.VULKAN, has_reflex=True)
        assert result["low_latency_mode"] == "off"
        assert result.get("use_reflex") is True

    def test_llm_not_assumed_for_dx12_without_reflex(self):
        """Test driver LLM is not assumed useful for DX12 without Reflex."""
        result = get_llm_recommendation(GraphicsAPI.DX12, has_reflex=False)
        assert result["low_latency_mode"] == "off"
        assert "dx12" in result["reason"]
        assert "use_reflex" not in result or result.get("use_reflex") is not True


class TestFightingGameConfig:
    """Tests for fighting game VRR configuration."""

    def test_vrr_config_default(self):
        """Test default VRR config for fighting games."""
        config = get_fighting_game_config(144)
        assert config["gsync"] is True
        assert config["vsync_nvcp"] is True
        assert config["vsync_ingame"] is False
        assert config["low_latency_mode"] == "on"
        assert config["fps_cap"] == 141

    def test_competitive_tearing_config(self):
        """Test competitive config that accepts tearing."""
        config = get_fighting_game_config(144, accept_tearing=True)
        assert config["gsync"] is False
        assert config["vsync_nvcp"] is False
        assert config["fps_cap"] is None


class TestHighRefreshBenefit:
    """Tests for high refresh rate benefit calculations."""

    def test_scanout_reduction(self):
        """Test scanout time reduction calculation."""
        result = get_high_refresh_benefit(60, 240)
        assert result["base_scanout_ms"] == 16.6
        assert result["target_scanout_ms"] == 4.2
        assert result["scanout_reduction_ms"] == pytest.approx(12.4, rel=0.01)

    def test_percentage_reduction(self):
        """Test percentage reduction is calculated."""
        result = get_high_refresh_benefit(60, 240)
        # (16.6 - 4.2) / 16.6 * 100 ≈ 74.7%
        assert result["scanout_reduction_percent"] > 70
