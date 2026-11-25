# src/darwin_cli/loader.py

"""
Config-dict conversion helpers and constraint parsing.
"""

from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from darwin_cli.base import Constraint, Param, ValidationRule

# ============================================================
# Helpers
# ============================================================


def _is_valid_help(value: Any) -> bool:
    return isinstance(value, str) or callable(value)


def _is_valid_action(value: Any) -> bool:
    return isinstance(value, str) or callable(value)


def _callable_name(func: Callable) -> str:
    if hasattr(func, "__name__"):
        return func.__name__
    if hasattr(func, "__class__"):
        return func.__class__.__name__
    return "unknown"


# ============================================================
# Param conversion
# ============================================================


def parse_params_from_config(config: Dict[str, Dict[str, Any]]) -> List[Param]:
    """Convert a config dict into Param objects.

    Config format::

        {
            "param_name": {
                "type": "str",                 # or ValidationRule, or rule dict
                "required": true,
                "default": "value",            # or Callable
                "help": "description",         # or Callable
                "action": "action_name",       # or Callable
                "depends_on": ["other"],
                "validation": {"min": 1, "max": 100}
            }
        }
    """
    return [_parse_single_param(name, definition) for name, definition in config.items()]


def _parse_single_param(name: str, definition: Dict[str, Any]) -> Param:
    param_type, validation = _parse_type_and_validation(definition)

    help_value = definition.get("help", "")
    if not _is_valid_help(help_value):
        help_value = str(help_value) if help_value is not None else ""

    action_value = definition.get("action")
    if action_value is not None and not _is_valid_action(action_value):
        raise ValueError(
            f"Action of parameter '{name}' must be str or Callable, got {type(action_value)}"
        )

    default_value = definition.get("default")

    depends_on = definition.get("depends_on")
    if depends_on is not None:
        if not isinstance(depends_on, list):
            raise ValueError(f"depends_on of '{name}' must be a list, got {type(depends_on)}")
        if not all(isinstance(d, str) for d in depends_on):
            raise ValueError(f"depends_on of '{name}' must contain only strings")

    return Param(
        name=name,
        type=param_type,
        required=definition.get("required", False),
        default=default_value,
        help=help_value,
        action=action_value,
        validation=validation,
        depends_on=depends_on,
    )


def _parse_type_and_validation(definition: Dict[str, Any]) -> tuple:
    raw_type = definition.get("type", "str")
    raw_validation = definition.get("validation")

    if isinstance(raw_type, dict):
        return _to_validation_rule(raw_type), None
    if isinstance(raw_type, ValidationRule):
        return raw_type, None
    if isinstance(raw_type, str):
        validation_rule: Optional[ValidationRule] = None
        if raw_validation is not None:
            if isinstance(raw_validation, dict):
                validation_rule = _to_validation_rule(raw_validation)
            elif isinstance(raw_validation, ValidationRule):
                validation_rule = raw_validation
        return raw_type, validation_rule
    return "str", None


def _to_validation_rule(data: Union[Dict[str, Any], ValidationRule]) -> ValidationRule:
    if isinstance(data, ValidationRule):
        return data
    if not isinstance(data, dict):
        raise ValueError(f"Cannot convert to ValidationRule: {data}")
    return ValidationRule(
        choices=data.get("choices"),
        min=data.get("min"),
        max=data.get("max"),
        min_length=data.get("min_length"),
        max_length=data.get("max_length"),
        pattern=data.get("pattern"),
        custom=data.get("custom"),
    )


# ============================================================
# Constraint conversion
# ============================================================

KNOWN_RULES = {
    "mutually_exclusive",
    "together",
    "requires",
    "exclusive_with",
    "at_least_one",
}


def parse_constraints(config: List[Union[Dict[str, Any], Constraint]]) -> List[Constraint]:
    """Convert a list of constraint dicts into Constraint objects.

    Supported forms::

        {"rule": "mutually_exclusive", "params": ["date", "year"]}
        {"rule": "together", "params": ["user", "password"]}
        {"rule": "requires", "param": "type", "requires": "source"}
        {"rule": "exclusive_with", "param": "date", "group": ["start_date", "end_date"]}
        {"rule": "at_least_one", "params": ["source", "file"]}

    An optional ``message`` overrides the default English error message.
    An optional ``include_generated`` (default ``False``) also counts values
    produced by Actions when checking the rule.
    """
    result: List[Constraint] = []
    for item in config or []:
        if isinstance(item, Constraint):
            result.append(item)
            continue
        if not isinstance(item, dict):
            raise ValueError(f"Constraint must be a dict or Constraint, got {type(item)}")

        rule = item.get("rule")
        if rule not in KNOWN_RULES:
            raise ValueError(
                f"Unknown constraint rule '{rule}'. Expected one of: {sorted(KNOWN_RULES)}"
            )

        result.append(
            Constraint(
                rule=rule,
                params=list(item.get("params") or []),
                param=item.get("param"),
                group=list(item.get("group") or []),
                requires=item.get("requires"),
                message=item.get("message"),
                include_generated=bool(item.get("include_generated", False)),
            )
        )
    return result


# ============================================================
# Groups: load-time compilation of declarative relations
# ============================================================

# Ordered tuple so rule generation has a stable order. ``KNOWN_RULES`` above
# is the equivalent set used by ``parse_constraints``.
RELATION_RULES = (
    "mutually_exclusive",
    "together",
    "at_least_one",
    "exclusive_with",
    "requires",
)

KNOWN_PARAM_KEYS = {
    "type",
    "required",
    "default",
    "help",
    "action",
    "validation",
    "depends_on",
} | set(RELATION_RULES)

# Keys whose values are references; '@group' is illegal in all of them.
REF_KEYS = set(RELATION_RULES) | {"group", "depends_on"}


def validate_param_definitions(definitions: Dict[str, Dict[str, Any]]) -> None:
    """Validate the param layer of a config.

    The param layer is deliberately small: a relation is **one-to-one** and
    names exactly one other parameter. Group references and group membership
    belong to the ``groups`` section only. Unknown keys are rejected rather
    than silently dropped, so a typo can never disable a relation.
    """
    for name, definition in definitions.items():
        if not isinstance(definition, dict):
            raise ValueError(f"Definition of parameter '{name}' must be a dict")
        for key, value in definition.items():
            if key == "group":
                raise ValueError(
                    f"'{name}.group' is not supported; "
                    "declare group members in the 'groups' section"
                )
            if key not in KNOWN_PARAM_KEYS:
                raise ValueError(
                    f"Unknown key '{name}.{key}'. "
                    f"Expected one of: {sorted(KNOWN_PARAM_KEYS)}"
                )
            if key in REF_KEYS:
                items = value if isinstance(value, list) else [value]
                for item in items:
                    if isinstance(item, str) and item.startswith("@"):
                        raise ValueError(
                            f"'{name}.{key}' references group '{item}': "
                            "param definitions cannot reference groups; "
                            "use a parameter name, or move the relation to 'groups'"
                        )
        for rule in RELATION_RULES:
            if rule not in definition:
                continue
            value = definition[rule]
            if isinstance(value, list):
                raise ValueError(
                    f"'{name}.{rule}' is a list: param-level relations are "
                    "one-to-one; use a single parameter name "
                    '(e.g. "together": "end_date"). For a relation among '
                    "several params, define a group."
                )
            if not isinstance(value, str):
                raise ValueError(
                    f"'{name}.{rule}' must be a single parameter name (str), "
                    f"got {type(value).__name__}"
                )
            if value == name:
                raise ValueError(f"'{name}.{rule}' cannot reference itself")


def param_definitions_from_objects(params: List[Param]) -> Dict[str, Dict[str, Any]]:
    """Extract the relation subset of a list of ``Param`` objects.

    ``CliApp(params=[Param(...)])`` and the config form then share the same
    compiler. Only relation fields and ``depends_on`` are relevant here.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for p in params:
        definition: Dict[str, Any] = {}
        for rule in RELATION_RULES:
            value = getattr(p, rule, None)
            if value is not None:
                definition[rule] = value
        if p.depends_on is not None:
            definition["depends_on"] = p.depends_on
        result[p.name] = definition
    return result


def split_groups_section(
    groups: Dict[str, Any],
) -> Tuple[Dict[str, List[Any]], Dict[str, Dict[str, Any]]]:
    """Split ``groups`` into member lists and relation rules.

    A group value is either a **list** (pure members) or a **dict** holding
    ``members`` plus zero or more relation rules (keys named after the 5 rules).
    """
    explicit: Dict[str, List[Any]] = {}
    rules: Dict[str, Dict[str, Any]] = {}
    for tag, value in (groups or {}).items():
        if not isinstance(tag, str) or not tag.startswith("@"):
            raise ValueError(f"Group key must start with '@': {tag!r}")
        if isinstance(value, list):
            explicit[tag] = list(value)
            rules[tag] = {}
        elif isinstance(value, dict):
            if "members" not in value:
                raise ValueError(
                    f"Group '{tag}' has no 'members'; group membership is "
                    "declared only in the 'groups' section"
                )
            members = value["members"]
            if not isinstance(members, list):
                raise ValueError(f"'{tag}.members' must be a list")
            explicit[tag] = list(members)
            group_rules = {k: v for k, v in value.items() if k != "members"}
            for rule in group_rules:
                if rule not in KNOWN_RULES:
                    raise ValueError(
                        f"Unknown group rule '{tag}.{rule}'. "
                        f"Expected one of: {sorted(KNOWN_RULES)}"
                    )
            rules[tag] = group_rules
        else:
            raise ValueError(
                f"Definition of group '{tag}' must be a list or dict, "
                f"got {type(value).__name__}"
            )
    return explicit, rules


def resolve_groups(explicit: Dict[str, List[Any]]) -> Dict[str, List[str]]:
    """Expand nested ``@group`` references into flat parameter-name lists.

    DFS with an explicit visiting stack, so cycles (including self cycles) are
    reported with the actual path instead of recursing forever. Membership has
    exactly one source: the ``groups`` section.
    """
    known = set(explicit)
    resolved: Dict[str, List[str]] = {}
    visiting: List[str] = []

    def resolve(tag: str) -> List[str]:
        if tag in resolved:
            return resolved[tag]
        if tag in visiting:
            cycle = visiting[visiting.index(tag):] + [tag]
            raise ValueError("Group cycle detected: " + " -> ".join(cycle))
        visiting.append(tag)
        out: List[str] = []
        for item in explicit.get(tag, []):
            if not isinstance(item, str):
                raise ValueError(
                    f"Members of group '{tag}' must be strings, "
                    f"got {type(item).__name__}"
                )
            if item.startswith("@"):
                if item not in known:
                    raise ValueError(f"Undefined group '{item}' (referenced by '{tag}')")
                out.extend(resolve(item))
            else:
                out.append(item)
        out = list(dict.fromkeys(out))  # de-duplicate, keep declaration order
        visiting.pop()
        if not out:
            raise ValueError(f"Group '{tag}' has no members")
        resolved[tag] = out
        return out

    for tag in sorted(known):
        resolve(tag)
    return resolved


def expand(
    names: Iterable[str],
    resolved: Dict[str, List[str]],
    drop: Optional[str] = None,
) -> List[str]:
    """Replace each ``@group`` with its resolved flat members; de-duplicate.

    ``drop`` removes the subject itself, which matters when the subject also
    belongs to the target group (otherwise a parameter would conflict with
    itself forever).
    """
    out: List[str] = []
    for item in names:
        if not isinstance(item, str):
            raise ValueError(
                f"Group references must be strings, got {type(item).__name__}"
            )
        if item.startswith("@"):
            if item not in resolved:
                raise ValueError(f"Undefined group '{item}'")
            out.extend(resolved[item])
        else:
            out.append(item)
    out = list(dict.fromkeys(out))
    if drop is not None:
        out = [name for name in out if name != drop]
    return out


def _make_rules(rule: str, subject: str, targets: List[str]) -> List[Constraint]:
    if rule == "exclusive_with":
        return [Constraint(rule=rule, param=subject, group=list(targets))]
    if rule == "requires":
        return [Constraint(rule=rule, param=subject, requires=t) for t in targets]
    return [Constraint(rule=rule, params=[subject] + list(targets))]


def _constraint_key(c: Constraint) -> tuple:
    return (
        c.rule,
        tuple(sorted(c.params)),
        c.param,
        tuple(sorted(c.group)),
        c.requires,
        c.message,
        bool(c.include_generated),
    )


def _dedupe(rules: List[Constraint]) -> List[Constraint]:
    seen, out = set(), []
    for c in rules:
        key = _constraint_key(c)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def compile_constraints(
    definitions: Dict[str, Dict[str, Any]],
    groups: Optional[Dict[str, Any]] = None,
    constraints: Optional[List[Union[Dict[str, Any], Constraint]]] = None,
) -> List[Constraint]:
    """Compile all three declaration layers into one flat constraint list.

    Layers
    ------
    * **param definitions**: one-to-one relations (a single parameter name).
    * **``groups``**: ``true`` -> (a) one N-ary rule among the group's own
      members; a list -> (b) the group's relation to a third party (another
      group and/or a parameter), expanded per member.
    * **top-level ``constraints``**: unchanged, except that ``@group``
      references in ``params`` / ``group`` are expanded. Custom ``message`` and
      ``include_generated`` stay available here.

    The runtime never sees groups: everything becomes a plain ``Constraint``
    evaluated by ``constraints.py``. ``at_least_one`` is sorted last because it
    is a fallback hint and the engine reports the first violation only.
    """
    validate_param_definitions(definitions)
    explicit, group_rules = split_groups_section(groups or {})
    resolved = resolve_groups(explicit)
    rules: List[Constraint] = []

    # (1) group-level rules
    for tag, spec in group_rules.items():
        for rule, value in spec.items():
            if value is True:
                rules.append(Constraint(rule=rule, params=list(resolved[tag])))
            elif isinstance(value, list):
                for member in resolved[tag]:
                    targets = expand(value, resolved, drop=member)
                    if targets:
                        rules.extend(_make_rules(rule, member, targets))
            else:
                raise ValueError(
                    f"Group rule '{tag}.{rule}' must be true or a list, "
                    f"got {type(value).__name__}"
                )

    # (2) param-level inline relations (one-to-one)
    for name, definition in definitions.items():
        for rule in RELATION_RULES:
            if rule not in definition:
                continue
            targets = expand([definition[rule]], resolved, drop=name)
            if targets:
                rules.extend(_make_rules(rule, name, targets))

    # (3) top-level constraints (backward compatible)
    expanded: List[Union[Dict[str, Any], Constraint]] = []
    for item in constraints or []:
        if isinstance(item, Constraint):
            expanded.append(item)
            continue
        if not isinstance(item, dict):
            raise ValueError(
                f"Constraint must be a dict or Constraint, got {type(item)}"
            )
        entry = dict(item)
        for key in ("params", "group"):
            if isinstance(entry.get(key), list):
                entry[key] = expand(entry[key], resolved)
        expanded.append(entry)
    rules.extend(parse_constraints(expanded))

    rules = _dedupe(rules)
    rules.sort(key=lambda c: c.rule == "at_least_one")
    return rules


# ============================================================
# Convenience helpers
# ============================================================


def get_param_by_name(params: List[Param], name: str) -> Optional[Param]:
    for p in params:
        if p.name == name:
            return p
    return None


def merge_params(base: List[Param], override: List[Param]) -> List[Param]:
    """Merge two lists; same-name entries in override win."""
    param_map = {p.name: p for p in base}
    for p in override:
        param_map[p.name] = p
    return list(param_map.values())


def params_to_dict(params: List[Param]) -> Dict[str, Dict[str, Any]]:
    """Serialize params for debugging. Callables become placeholder strings."""
    result: Dict[str, Dict[str, Any]] = {}
    for p in params:
        definition: Dict[str, Any] = {}
        if isinstance(p.type, ValidationRule):
            definition["type"] = _validation_rule_to_dict(p.type)
        else:
            definition["type"] = p.type
        if p.required:
            definition["required"] = True
        if p.default is not None:
            definition["default"] = (
                f"<Callable: {_callable_name(p.default)}>"
                if callable(p.default)
                else p.default
            )
        if p.help:
            definition["help"] = (
                f"<Callable: {_callable_name(p.help)}>" if callable(p.help) else p.help
            )
        if p.action:
            definition["action"] = (
                f"<Callable: {_callable_name(p.action)}>" if callable(p.action) else p.action
            )
        if p.validation:
            definition["validation"] = _validation_rule_to_dict(p.validation)
        if p.depends_on:
            definition["depends_on"] = p.depends_on
        for key in RELATION_RULES:
            value = getattr(p, key, None)
            if value is not None:
                definition[key] = value
        result[p.name] = definition
    return result


def _validation_rule_to_dict(rule: ValidationRule) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key in (
        "choices",
        "min",
        "max",
        "min_length",
        "max_length",
        "pattern",
        "custom",
    ):
        value = getattr(rule, key)
        if value is not None:
            result[key] = value
    return result
