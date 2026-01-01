from ruamel.yaml import YAML
from pathlib import Path
from tempfile import TemporaryDirectory

file = Path("oscar_neira_unified_CV.yaml")
TAILORED_DICT = "sections"

yaml = YAML()

data = yaml.load(file)
locales = data['locale']

dict_locales = dict()
for key in locales:
    print(key)


def deep_merge(a, b): 
    """Si a y b son diccionarios, se funden, si no se devuelve b"""
    if isinstance(a, dict) and isinstance(b, dict):
        result = dict(a)
        for k, vb in b.items():
            va = result.get(k)
            if isinstance(va, dict) and isinstance(vb, dict):
                result[k] = deep_merge(va, vb)
            else:
                result[k] = vb
        return result
    # para listas el criterio podría variar
    return b

def build_for_lang(node, lang: str, langs_set: set[str]):
    if isinstance(node, dict):
        # este nodo tiene clave de idiomas?
        langs_key_present = [k for k in node.keys() if k in langs_set]
        if langs_key_present:
            # Las claves comunes deben estar siempre
            common = {k: v for k, v in node.items() if k not in langs_set}
            common_sub = build_for_lang(common, lang, langs_set)
            # Seleccionar la clave del idioma especifico
            selected = node.get(lang, None)
            if selected is None:
                # No hay idioma, devolver la parte comun
                return common_sub
            selected_sub = build_for_lang(selected, lang, langs_set)
            # Fusioanr comun y seleccionado
            return deep_merge(common_sub, selected_sub)
        # sin claves de idioma: procesar como dict normal
        return {k: build_for_lang(v, lang, langs_set) for k, v in node.items()}
    elif isinstance(node, list):
        return [build_for_lang(item, lang, langs_set) for item in node]
    else:
        return node


def hoist_languages_to_top(data: dict, languages: list[str]) -> dict:
    lang_set = set(languages)
    return {lang: build_for_lang(data, lang, set(languages)) for lang in languages}

result = hoist_languages_to_top(data, locales)

def fix_locale_path(locale_data):
    """Expands LOCALE if settings paths"""
    for locale, data in locale_data.items():
        if settings := data['settings']:
            if render_command := settings['render_command']:
                for k, v in render_command.items():
                    if k.endswith("_path"):
                        render_command[k] = v.replace("LOCALE", locale)
    return locale_data

result = fix_locale_path(result)

def fix_tailored_locale_headings(locale_data):
    """Gets tailored translations from locale section"""
    for locale, data in locale_data.items():
        if locale_settings := data['locale']:
            if tailored := locale_settings.pop(TAILORED_DICT, None):
                print(tailored)    
                sections = data['cv']['sections']
                new_sections = {tailored.get(k, k): v for k, v in sections.items()}
                data['cv']['sections'] = new_sections
    
    return locale_data
    
result = fix_tailored_locale_headings(result)



import pprint
pprint.pprint(result)


for lang, lang_data in result.items():
    with TemporaryDirectory() as tempdir:
    
        lang_file = Path(tempdir) / f"{lang}_CV.yaml"
        yaml.dump(lang_data, lang_file)
        # from rendercv.cli.render_command.render_command import run_rendercv
        from rendercv.cli.render_command.render_command import cli_command_render
        from typer import Context
        ctx = Context("dummy", allow_extra_args=False, allow_interspersed_args=False, ignore_unknown_options=True)
        cli_command_render(lang_file, extra_data_model_override_arguments=ctx)
    