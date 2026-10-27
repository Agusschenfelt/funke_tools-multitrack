import pytest
from pydantic import ValidationError

from audio_core.models import Section, SectionName, Sections, StagePackOptions


def test_sections_roundtrip_from_json() -> None:
    raw = (
        '{"source": "song.wav", "sections": ['
        '{"name": "intro", "start": 0}, {"name": "verse_2", "start": 30.5, "label": "V2"}]}'
    )
    parsed = Sections.model_validate_json(raw)
    assert parsed.sections[1].name is SectionName.VERSE_2
    assert Sections.model_validate_json(parsed.model_dump_json()) == parsed


def test_sections_source_is_optional() -> None:
    assert Sections(sections=[]).source is None


def test_unknown_section_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Section(name="refrain", start=1.0)  # type: ignore[arg-type]


def test_negative_start_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Section(name=SectionName.VERSE, start=-0.1)


def test_unsorted_sections_are_rejected() -> None:
    with pytest.raises(ValidationError, match="sorted"):
        Sections(
            sections=[
                Section(name=SectionName.VERSE, start=20),
                Section(name=SectionName.CHORUS, start=10),
            ]
        )


def test_duplicate_starts_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        Sections(
            sections=[
                Section(name=SectionName.VERSE, start=10),
                Section(name=SectionName.CHORUS, start=10),
            ]
        )


def test_stage_pack_options_defaults() -> None:
    options = StagePackOptions(destination="daw")
    assert options.count_in_bars == 1
    assert options.click_sound == "classic"
    assert options.subdivision == "quarter"
    assert options.straight_grid is False
    assert options.sample_rate == 44100
    assert options.include_vocals is False
    assert options.language == "es"


@pytest.mark.parametrize(
    "field, value",
    [
        ("destination", "prime"),
        ("count_in_bars", 3),
        ("sample_rate", 96000),
        ("click_sound", "laser"),
        ("language", "fr"),
    ],
)
def test_stage_pack_options_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        StagePackOptions(**{"destination": "daw", field: value})  # type: ignore[arg-type]
