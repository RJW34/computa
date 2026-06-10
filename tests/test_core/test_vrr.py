"""Tests for VRR optimization knowledge base."""

from __future__ import annotations

import pytest

from abso.core.vrr import (
    OW2_REFLEX_GSYNC_CAP_POLICY,
    REFLEX_GSYNC_FPS_CAPS,
    VRR_FPS_CAPS,
    FrameLimiterType,
    GraphicsAPI,
    get_best_ingame_preset,
    get_fighting_game_config,
    get_high_refresh_benefit,
    get_limiter_recommendation,
    get_llm_recommendation,
    get_reflex_gsync_fps_cap,
    get_vrr_fps_cap,
    get_vrr_fps_cap_for_policy,
)


class TestVRRFPSCap:
    """Tests for VRR FPS cap calculations.

    ABSO uses the Blur Busters G-SYNC 101 ``refresh - 3`` convention as the
    static V-SYNC safety boundary. Reflex presence does not change this —
    Reflex is a separate dynamic latency control; the static cap is just
    the ceiling that keeps V-SYNC from engaging during normal play.
    """

    def test_get_vrr_fps_cap_low_refresh(self):
        """Common low-refresh presets all follow refresh - 3."""
        assert get_vrr_fps_cap(60) == 57
        assert get_vrr_fps_cap(120) == 117
        assert get_vrr_fps_cap(144) == 141
        assert get_vrr_fps_cap(165) == 162

    def test_get_vrr_fps_cap_high_refresh(self):
        """High-refresh presets also follow refresh - 3 (no separate margin)."""
        assert get_vrr_fps_cap(240) == 237
        assert get_vrr_fps_cap(280) == 277
        assert get_vrr_fps_cap(300) == 297
        assert get_vrr_fps_cap(360) == 357
        assert get_vrr_fps_cap(480) == 477

    def test_get_vrr_fps_cap_fallback_calculation(self):
        """Non-preset rates fall through to refresh - 3 inline."""
        assert get_vrr_fps_cap(85) == 82
        assert get_vrr_fps_cap(155) == 152
        assert get_vrr_fps_cap(220) == 217
        assert get_vrr_fps_cap(330) == 327
        assert get_vrr_fps_cap(540) == 537

    def test_get_vrr_fps_cap_reflex_arg_is_noop(self):
        """``reflex_active`` is accepted but ignored — both paths use refresh - 3.

        The previous Reflex-aware variant was synthesized on unverified
        scaling rationale; the parameter is retained for callsite stability
        only and must not change the return value.
        """
        assert get_vrr_fps_cap(300, reflex_active=True) == 297
        assert get_vrr_fps_cap(300, reflex_active=False) == 297
        assert get_vrr_fps_cap(300, reflex_active=None) == 297
        assert get_vrr_fps_cap(300) == 297

    def test_get_vrr_fps_cap_rounds_float_input(self):
        """Float refresh rates round to nearest integer before lookup."""
        assert get_vrr_fps_cap(299.99) == 297  # rounds to 300
        assert get_vrr_fps_cap(143.7) == 141   # rounds to 144

    def test_vrr_fps_caps_dict_has_common_values(self):
        """VRR_FPS_CAPS contains all expected refresh-rate presets."""
        for hz in (60, 144, 165, 240, 280, 300, 360, 480, 500):
            assert hz in VRR_FPS_CAPS, f"missing preset {hz}"
            assert VRR_FPS_CAPS[hz] == hz - 3, f"{hz} preset is not refresh - 3"

    def test_get_reflex_gsync_fps_cap_known_rates(self):
        """OW2 Reflex/G-SYNC policy uses the wider current Reflex margin."""
        assert get_reflex_gsync_fps_cap(165) == 157
        assert get_reflex_gsync_fps_cap(240) == 224
        assert get_reflex_gsync_fps_cap(300) == 276
        assert REFLEX_GSYNC_FPS_CAPS[300] == 276

    def test_get_reflex_gsync_fps_cap_fallback_calculation(self):
        """Less-common refresh rates use the same frame-time margin."""
        assert get_reflex_gsync_fps_cap(280) == 259
        assert get_reflex_gsync_fps_cap(299.99) == 276

    def test_get_vrr_fps_cap_for_policy(self):
        """Policy selection is explicit so non-OW games keep refresh - 3."""
        assert get_vrr_fps_cap_for_policy(300) == 297
        assert get_vrr_fps_cap_for_policy(300, "refresh_minus_3") == 297
        assert get_vrr_fps_cap_for_policy(300, OW2_REFLEX_GSYNC_CAP_POLICY) == 276


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

        # 300Hz monitor -> 297 target -> 240 is best preset
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
            available_presets=[60, 120],  # 120 is far from 297 (refresh - 3 at 300Hz)
        )
        assert result["limiter"] == FrameLimiterType.RTSS
        assert result["fps_cap"] == 297  # refresh - 3 at 300Hz (Blur Busters G-SYNC 101)

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
