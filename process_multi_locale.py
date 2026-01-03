"""
This script processes a multi-locale RenderCV YAML file and generates individual
localized YAML files, then renders them using RenderCV.
"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from ruamel.yaml import YAML
from rendercv.schema.models.locale.locale import discover_other_locales
from rendercv.cli.render_command.render_command import cli_command_render
from typer import Context

# Constant for the tailored sections dictionary key
TAILORED_DICT = "sections"


def deep_merge(a, b):
    """
    Recursively merges two dictionaries. If a and b are both dictionaries,
    their keys are merged. Otherwise, b is returned.

    Args:
        a: The base dictionary or value.
        b: The dictionary or value to merge into a.

    Returns:
        The merged dictionary or the value b.
    """
    if isinstance(a, dict) and isinstance(b, dict):
        result = dict(a)
        for k, vb in b.items():
            va = result.get(k)
            if isinstance(va, dict) and isinstance(vb, dict):
                result[k] = deep_merge(va, vb)
            else:
                result[k] = vb
        return result
    return b


def build_for_lang(node, lang: str, langs_set: set[str]):
    """
    Recursively processes a node (dict, list, or scalar) and selects the
    appropriate content based on the target language.

    Args:
        node: The YAML node to process.
        lang: The target language string.
        langs_set: A set of all available language keys in the document.

    Returns:
        The processed node with language-specific content selected and merged.
    """
    if isinstance(node, dict):
        # Check if this node contains language-specific keys
        langs_key_present = [k for k in node.keys() if k in langs_set]
        if langs_key_present:
            # Extract common fields that are not language-specific
            common = {k: v for k, v in node.items() if k not in langs_set}
            common_sub = build_for_lang(common, lang, langs_set)

            # Select the specific language content if it exists
            selected = node.get(lang, None)
            if selected is None:
                # If the specific language is not present, return the common part
                return common_sub

            selected_sub = build_for_lang(selected, lang, langs_set)

            # Merge common content with the language-specific content
            return deep_merge(common_sub, selected_sub)

        # If no language keys are present, process as a normal dictionary
        return {k: build_for_lang(v, lang, langs_set) for k, v in node.items()}
    elif isinstance(node, list):
        # Recursively process each item in a list
        return [build_for_lang(item, lang, langs_set) for item in node]
    else:
        # Return scalar values as is
        return node


def hoist_languages_to_top(data: dict, languages: list[str]) -> dict:
    """
    Creates a dictionary where keys are languages and values are the
    processed CV data for that language.

    Args:
        data: The original input dictionary.
        languages: A list of language strings.

    Returns:
        A dictionary mapping each language to its processed data.
    """
    return {
        lang: build_for_lang(data, lang, set(languages)) for lang in languages
    }


def fix_locale_paths(locale_data: dict) -> dict:
    """
    Replaces the 'LOCALE' keyword in settings paths with the actual locale string.

    Args:
        locale_data: A dictionary mapping locales to their processed data.

    Returns:
        The updated dictionary with expanded paths.
    """
    for locale, data in locale_data.items():
        if "settings" in data and data["settings"]:
            settings = data["settings"]
            if "render_command" in settings and settings["render_command"]:
                render_command = settings["render_command"]
                for k, v in render_command.items():
                    if isinstance(v, str) and k.endswith("_path"):
                        if "LOCALE" not in v:
                            raise ValueError(
                                f"Path '{k}' must include 'LOCALE' keyword."
                            )
                        render_command[k] = v.replace("LOCALE", locale)
    return locale_data


def fix_tailored_locale_headings(locale_data: dict) -> dict:
    """
    Applies tailored section title translations from the 'locale' configuration.

    Args:
        locale_data: A dictionary mapping locales to their processed data.

    Returns:
        The updated dictionary with localized section titles.
    """
    for locale, data in locale_data.items():
        if "locale" in data and data["locale"]:
            locale_settings = data["locale"]
            # Look for the 'sections' key within the locale settings
            if tailored := locale_settings.pop(TAILORED_DICT, None):
                if "cv" in data and "sections" in data["cv"]:
                    sections = data["cv"]["sections"]
                    # Rename section keys based on tailored translations
                    new_sections = {
                        tailored.get(k, k): v for k, v in sections.items()
                    }
                    data["cv"]["sections"] = new_sections
    return locale_data


def process_multi_locale_file(file_path: Path):
    """
    Loads a multi-locale YAML file, processes it for each locale, and renders
    the resulting CVs.

    Args:
        file_path: The path to the multi-locale YAML file.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    yaml = YAML()
    data = yaml.load(file_path)

    if "locale" not in data:
        raise ValueError("The input file must contain a 'locale' key.")

    locales = data["locale"]
    available_locales = [other_locale().language_iso_639_1 for other_locale in discover_other_locales()]
    available_locales.append("en")  # Add English to the list of available locales

    # Validate that all requested locales are supported by RenderCV
    for locale in locales:
        if locale not in available_locales:
            raise ValueError(f"Locale {locale} is not available in RenderCV.")

    # Process data to separate content by language
    processed_data = hoist_languages_to_top(data, locales)

    # Expand paths and apply tailored headings
    processed_data = fix_locale_paths(processed_data)
    processed_data = fix_tailored_locale_headings(processed_data)

    # Render each localized CV
    for lang, lang_data in processed_data.items():
        with TemporaryDirectory() as tempdir:
            temp_path = Path(tempdir)
            lang_file = temp_path / f"{lang}_CV.yaml"
            yaml.dump(lang_data, lang_file)

            # Prepare a dummy context for the Typer command
            ctx = Context(
                cli_command_render,
                allow_extra_args=False,
                allow_interspersed_args=False,
                ignore_unknown_options=True,
            )

            print(f"Rendering CV for locale: {lang}")
            cli_command_render(lang_file, extra_data_model_override_arguments=ctx)


def main():
    """
    Entry point for the script when called from the command line.
    """
    parser = argparse.ArgumentParser(
        description="Process a multi-locale RenderCV YAML file."
    )
    parser.add_argument(
        "file", type=str, help="Path to the multi-locale YAML file."
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    try:
        process_multi_locale_file(file_path)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()