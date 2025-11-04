from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django import forms
from django.core.validators import RegexValidator
from django.test import SimpleTestCase

from core.utils import intake_forms as builder


class IntakeHelperFunctionTests(SimpleTestCase):
    def test_build_choices_skips_invalid_entries(self) -> None:
        raw = [
            {"value": "yes", "label": "Yes"},
            {"value": "", "label": "Missing value"},
            {"value": "no", "label": ""},
            {"label": "No value"},
            "plain-string",
        ]
        choices = builder._build_choices(raw)  # type: ignore[arg-type]
        self.assertEqual(choices, [("yes", "Yes")])

    def test_resolve_initial_prefers_provided_initial_then_default(self) -> None:
        cfg = {"key": "consent", "default": True, "type": "boolean"}
        provided = {"consent": False}
        self.assertFalse(builder._resolve_initial(cfg, provided))

        cfg_default = {"key": "consent", "default": True, "type": "boolean"}
        self.assertTrue(builder._resolve_initial(cfg_default, {}))

        cfg_none = {"key": "notes", "type": "text"}
        self.assertIsNone(builder._resolve_initial(cfg_none, {}))

    def test_attach_placeholder_and_width_mutate_widget(self) -> None:
        widget = forms.TextInput()
        builder._attach_placeholder(widget, "Enter name")
        builder._attach_widget_width(widget, {"width": "md"})
        self.assertEqual(widget.attrs["placeholder"], "Enter name")
        self.assertEqual(widget.attrs["data-width"], "md")

    def test_charfield_appends_regex_validator(self) -> None:
        field = builder._charfield(
            {"settings": {"pattern": r"^\d+$", "pattern_message": "Digits only"}},
            {"required": False},
        )
        self.assertIsInstance(field, forms.CharField)
        self.assertTrue(any(isinstance(validator, RegexValidator) for validator in field.validators))

    def test_number_and_decimal_fields_apply_limits(self) -> None:
        number = builder._number_field({"settings": {"min_value": 1, "max_value": 10}}, {"required": True})
        decimal_field = builder._decimal_field(
            {"settings": {"min_value": "0.50", "max_value": "9.99", "decimal_places": 3, "max_digits": 6}},
            {"required": True},
        )
        self.assertEqual(number.min_value, 1)
        self.assertEqual(number.max_value, 10)
        self.assertEqual(decimal_field.min_value, Decimal("0.50"))
        self.assertEqual(decimal_field.max_value, Decimal("9.99"))
        self.assertEqual(decimal_field.decimal_places, 3)
        self.assertEqual(decimal_field.max_digits, 6)

    def test_choice_field_builds_correct_widget(self) -> None:
        cfg = {
            "choices": [
                {"value": "a", "label": "Option A"},
                {"value": "b", "label": "Option B"},
            ],
            "placeholder": "Pick one",
        }
        field = builder._choice_field(cfg, {"required": False}, multiple=True, as_radio=False)
        self.assertIsInstance(field, forms.MultipleChoiceField)
        self.assertIsInstance(field.widget, forms.SelectMultiple)
        self.assertEqual(field.widget.attrs["placeholder"], "Pick one")


class BuildIntakeFormTests(SimpleTestCase):
    def _dummy_form(self, schema):
        return SimpleNamespace(pk=42, normalized_schema=lambda: schema)

    def test_build_intake_form_creates_fields_for_each_section(self) -> None:
        schema = {
            "sections": [
                {
                    "fields": [
                        {"key": "full_name", "type": "text", "placeholder": "Name", "display": {"width": "lg"}},
                        {"key": "age", "type": "number", "settings": {"min_value": 18, "max_value": 65}},
                        {"key": "consent", "type": "boolean", "default": True},
                        {
                            "key": "preferences",
                            "type": "multiselect",
                            "choices": [
                                {"value": "peel", "label": "Peel"},
                                {"value": "laser", "label": "Laser"},
                            ],
                        },
                    ]
                }
            ],
            "meta": {"version": 2},
        }
        form = builder.build_intake_form(
            intake_form=self._dummy_form(schema),
            initial={"full_name": "Jane"},
        )

        self.assertIn("full_name", form.fields)
        self.assertEqual(form.fields["full_name"].widget.attrs["data-width"], "lg")
        self.assertEqual(form.fields["full_name"].initial, "Jane")
        self.assertIn("age", form.fields)
        self.assertEqual(form.fields["age"].min_value, 18)
        self.assertTrue(form.fields["consent"].initial)
        self.assertIsInstance(form.fields["preferences"], forms.MultipleChoiceField)
        self.assertEqual(form.intake_schema, schema)

    def test_build_intake_form_handles_empty_schema(self) -> None:
        form = builder.build_intake_form(intake_form=self._dummy_form(None))
        self.assertEqual(form.fields, {})
        self.assertEqual(form.intake_schema, {"sections": [], "meta": {}})
