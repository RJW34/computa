"""Tests for nvidia parsing module."""

from unittest.mock import patch

from abso.settings.nvidia.parsing import (
    parse_frame_rate_value,
    parse_low_latency_value,
    parse_nip_file,
    parse_power_management_value,
    parse_shader_cache_enabled_value,
    parse_shader_cache_value,
    parse_threaded_opt_value,
    parse_vsync_value,
)
from abso.settings.nvidia.presets import NvidiaSettingValues


class TestParseLowLatencyValue:
    """Tests for parse_low_latency_value function."""

    def test_returns_off_for_zero(self):
        """Test returns 'off' for value 0."""
        assert parse_low_latency_value("0") == "off"
        assert parse_low_latency_value("0x00000000") == "off"

    def test_returns_on_for_one(self):
        """Test returns 'on' for value 1."""
        assert parse_low_latency_value("1") == "on"
        assert parse_low_latency_value("0x00000001") == "on"

    def test_returns_ultra_for_two(self):
        """Test returns 'ultra' for value 2."""
        assert parse_low_latency_value("2") == "ultra"
        assert parse_low_latency_value("0x00000002") == "ultra"

    def test_returns_unknown_for_invalid_value(self):
        """Test returns 'unknown' for values outside range."""
        assert parse_low_latency_value("99") == "unknown"
        assert parse_low_latency_value("invalid") == "unknown"
        assert parse_low_latency_value("") == "unknown"


class TestParsePowerManagementValue:
    """Tests for parse_power_management_value function."""

    def test_returns_adaptive_for_zero(self):
        """Test returns 'adaptive' for value 0."""
        assert parse_power_management_value("0") == "adaptive"
        assert parse_power_management_value(str(NvidiaSettingValues.POWER_ADAPTIVE)) == "adaptive"

    def test_returns_prefer_max_for_one(self):
        """Test returns 'prefer_max_performance' for value 1."""
        assert parse_power_management_value("1") == "prefer_max_performance"

    def test_returns_optimal_for_two(self):
        """Test returns 'optimal' for value 2."""
        assert parse_power_management_value("2") == "optimal"

    def test_returns_unknown_for_invalid(self):
        """Test returns 'unknown' for invalid values."""
        assert parse_power_management_value("99") == "unknown"
        assert parse_power_management_value("bad") == "unknown"


class TestParseVsyncValue:
    """Tests for parse_vsync_value function."""

    def test_returns_off_for_zero(self):
        """Test returns 'off' for value 0."""
        assert parse_vsync_value("0") == "off"

    def test_returns_on_for_one(self):
        """Test returns 'on' for value 1."""
        assert parse_vsync_value("1") == "on"

    def test_returns_adaptive_for_two(self):
        """Test returns 'adaptive' for value 2."""
        assert parse_vsync_value("2") == "adaptive"

    def test_returns_adaptive_half_for_three(self):
        """Test returns 'adaptive_half' for value 3."""
        assert parse_vsync_value("3") == "adaptive_half"

    def test_returns_unknown_for_invalid(self):
        """Test returns 'unknown' for invalid values."""
        assert parse_vsync_value("10") == "unknown"
        assert parse_vsync_value("xyz") == "unknown"


class TestParseFrameRateValue:
    """Tests for parse_frame_rate_value function."""

    def test_returns_off_for_zero(self):
        """Test returns 'off' for value 0."""
        assert parse_frame_rate_value("0") == "off"

    def test_returns_number_for_positive(self):
        """Test returns string number for positive values."""
        assert parse_frame_rate_value("60") == "60"
        assert parse_frame_rate_value("144") == "144"
        assert parse_frame_rate_value("240") == "240"

    def test_handles_hex_values(self):
        """Test handles hex format."""
        assert parse_frame_rate_value("0x3C") == "60"  # 60 in hex

    def test_returns_unknown_for_invalid(self):
        """Test returns 'unknown' for invalid values."""
        assert parse_frame_rate_value("not_a_number") == "unknown"


class TestParseShaderCacheValue:
    """Tests for parse_shader_cache_value function."""

    def test_returns_off_for_zero(self):
        """A zero cache-size limit disables caching; it is not the default."""
        assert parse_shader_cache_value("0") == "off"

    def test_enabled_setting_does_not_parse_sizes(self):
        assert parse_shader_cache_enabled_value("0") == "off"
        assert parse_shader_cache_enabled_value("1") == "on"
        assert parse_shader_cache_enabled_value("2") == "unknown"
        assert parse_shader_cache_enabled_value("4294967295") == "unknown"

    def test_returns_unlimited_for_max_uint(self):
        """Test returns 'unlimited' for 0xFFFFFFFF."""
        assert parse_shader_cache_value("0xFFFFFFFF") == "unlimited"
        assert parse_shader_cache_value("4294967295") == "unlimited"

    def test_returns_mb_for_positive(self):
        """Test returns 'XMB' for positive values."""
        assert parse_shader_cache_value("1024") == "1024MB"
        assert parse_shader_cache_value("2048") == "2048MB"

    def test_returns_unknown_for_invalid(self):
        """Test returns 'unknown' for invalid values."""
        assert parse_shader_cache_value("invalid") == "unknown"


class TestParseThreadedOptValue:
    """Tests for parse_threaded_opt_value function."""

    def test_returns_auto_for_zero(self):
        """Test returns 'auto' for value 0."""
        assert parse_threaded_opt_value("0") == "auto"

    def test_returns_on_for_one(self):
        """Test returns 'on' for value 1."""
        assert parse_threaded_opt_value("1") == "on"

    def test_returns_off_for_two(self):
        """Test returns 'off' for value 2."""
        assert parse_threaded_opt_value("2") == "off"

    def test_returns_unknown_for_invalid(self):
        """Test returns 'unknown' for invalid values."""
        assert parse_threaded_opt_value("99") == "unknown"
        assert parse_threaded_opt_value("foo") == "unknown"


class TestParseNipFile:
    """Tests for parse_nip_file function."""

    def test_returns_empty_for_nonexistent_file(self, tmp_path):
        """Test returns empty dict for nonexistent file."""
        result = parse_nip_file(tmp_path / "nonexistent.nip")
        assert result == {}

    def test_parses_valid_nip_file(self, tmp_path):
        """Test parses valid NIP file correctly."""
        nip_content = '''<?xml version="1.0" encoding="utf-8"?>
<Root>
  <Profile name="Base Profile">
    <ProfileSetting id="0x007BA09E">
      <SettingValue>2</SettingValue>
    </ProfileSetting>
    <ProfileSetting id="0x1057EB71">
      <SettingValue>1</SettingValue>
    </ProfileSetting>
    <ProfileSetting id="0x00A879CF">
      <SettingValue>0</SettingValue>
    </ProfileSetting>
  </Profile>
</Root>'''
        nip_path = tmp_path / "test.nip"
        nip_path.write_text(nip_content, encoding="utf-8")

        result = parse_nip_file(nip_path)
        assert result.get("low_latency_mode") == "ultra"
        assert result.get("power_management") == "prefer_max_performance"
        assert result.get("vsync") == "off"

    def test_handles_global_driver_profile(self, tmp_path):
        """Test parses _Global_Driver_Profile profile name."""
        nip_content = '''<?xml version="1.0" encoding="utf-8"?>
<Root>
  <Profile name="_Global_Driver_Profile">
    <ProfileSetting id="0x007BA09E">
      <SettingValue>1</SettingValue>
    </ProfileSetting>
  </Profile>
</Root>'''
        nip_path = tmp_path / "test.nip"
        nip_path.write_text(nip_content, encoding="utf-8")

        result = parse_nip_file(nip_path)
        assert result.get("low_latency_mode") == "on"

    def test_handles_xml_parse_error(self, tmp_path):
        """Test handles invalid XML gracefully."""
        nip_path = tmp_path / "invalid.nip"
        nip_path.write_text("not valid xml {{{", encoding="utf-8")

        result = parse_nip_file(nip_path)
        assert result == {}

    def test_handles_empty_file(self, tmp_path):
        """Test handles empty file gracefully."""
        nip_path = tmp_path / "empty.nip"
        nip_path.write_text("", encoding="utf-8")

        result = parse_nip_file(nip_path)
        assert result == {}

    def test_handles_missing_setting_value(self, tmp_path):
        """Test handles missing SettingValue element."""
        nip_content = '''<?xml version="1.0" encoding="utf-8"?>
<Root>
  <Profile name="Base Profile">
    <ProfileSetting id="0x007BA09E">
    </ProfileSetting>
  </Profile>
</Root>'''
        nip_path = tmp_path / "test.nip"
        nip_path.write_text(nip_content, encoding="utf-8")

        result = parse_nip_file(nip_path)
        assert "low_latency_mode" not in result

    def test_parses_all_known_settings(self, tmp_path):
        """Test parses all known setting types."""
        nip_content = '''<?xml version="1.0" encoding="utf-8"?>
<Root>
  <Profile name="Base Profile">
    <ProfileSetting id="0x007BA09E"><SettingValue>2</SettingValue></ProfileSetting>
    <ProfileSetting id="0x1057EB71"><SettingValue>1</SettingValue></ProfileSetting>
    <ProfileSetting id="0x00A879CF"><SettingValue>2</SettingValue></ProfileSetting>
    <ProfileSetting id="0x10835002"><SettingValue>144</SettingValue></ProfileSetting>
    <ProfileSetting id="0x00198FFF"><SettingValue>1</SettingValue></ProfileSetting>
    <ProfileSetting id="0x00AC8497"><SettingValue>4294967295</SettingValue></ProfileSetting>
    <ProfileSetting id="0x20C1221E"><SettingValue>1</SettingValue></ProfileSetting>
  </Profile>
</Root>'''
        nip_path = tmp_path / "test.nip"
        nip_path.write_text(nip_content, encoding="utf-8")

        result = parse_nip_file(nip_path)
        assert result["low_latency_mode"] == "ultra"
        assert result["power_management"] == "prefer_max_performance"
        assert result["vsync"] == "adaptive"
        assert result["max_frame_rate"] == "144"
        assert result["shader_cache"] == "on"
        assert result["shader_cache_size"] == "unlimited"
        assert result["threaded_optimization"] == "on"

    def test_ignores_unknown_settings(self, tmp_path):
        """Test ignores unknown setting IDs."""
        nip_content = '''<?xml version="1.0" encoding="utf-8"?>
<Root>
  <Profile name="Base Profile">
    <ProfileSetting id="0xDEADBEEF">
      <SettingValue>999</SettingValue>
    </ProfileSetting>
  </Profile>
</Root>'''
        nip_path = tmp_path / "test.nip"
        nip_path.write_text(nip_content, encoding="utf-8")

        result = parse_nip_file(nip_path)
        assert result == {}

    def test_handles_os_error(self, tmp_path):
        """Test handles OS errors gracefully."""
        nip_path = tmp_path / "test.nip"

        with patch("builtins.open", side_effect=OSError("Permission denied")):
            result = parse_nip_file(nip_path)
            assert result == {}
