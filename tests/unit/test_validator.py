# tests/test_cli/unit/test_validator.py

"""
Test validator.py - Parameter validator
"""

import pytest
from darwin_cli.validator import Validator, create_validator
from darwin_cli.base import Param, ValidationRule
from darwin_cli.actions import ActionError


class TestValidator:
    """Test Validator """

    def test_validate_str(self):
        """Test str  validation"""
        param = Param(name="name", type="str")
        validator = Validator([param])

        result = validator.validate_one(param, "hello")
        assert result == "hello"

        result = validator.validate_one(param, 123)
        assert result == "123"

    def test_validate_int(self):
        """Test int  validation"""
        param = Param(name="count", type="int")
        validator = Validator([param])

        result = validator.validate_one(param, "123")
        assert result == 123

        result = validator.validate_one(param, 456)
        assert result == 456

        with pytest.raises(ActionError, match="type error"):
            validator.validate_one(param, "not a number")

    def test_validate_float(self):
        """Test float  validation"""
        param = Param(name="price", type="float")
        validator = Validator([param])

        result = validator.validate_one(param, "1.23")
        assert result == 1.23

        result = validator.validate_one(param, 4.56)
        assert result == 4.56

    def test_validate_bool_true(self):
        """Test bool  - True"""
        param = Param(name="enabled", type="bool")
        validator = Validator([param])

        #  True 
        for val in [True, "true", "1", "yes", "on", "t"]:
            result = validator.validate_one(param, val)
            assert result is True

    def test_validate_bool_false(self):
        """Test bool  - False"""
        param = Param(name="enabled", type="bool")
        validator = Validator([param])

        #  False 
        for val in [False, "false", "0", "no", "off", "f"]:
            result = validator.validate_one(param, val)
            assert result is False

    def test_validate_bool_invalid(self):
        """Test bool  -  no """
        param = Param(name="enabled", type="bool")
        validator = Validator([param])

        with pytest.raises(ActionError, match="type error"):
            validator.validate_one(param, "invalid")

    def test_validate_choices(self):
        """Test choices  validation"""
        param = Param(
            name="status",
            type="str",
            validation=ValidationRule(choices=["active", "inactive"]),
        )
        validator = Validator([param])

        result = validator.validate_one(param, "active")
        assert result == "active"

        with pytest.raises(ActionError, match="not in choices"):
            validator.validate_one(param, "pending")

    def test_validate_min_max(self):
        """Test min/max  validation"""
        param = Param(
            name="count",
            type="int",
            validation=ValidationRule(min=1, max=10),
        )
        validator = Validator([param])

        result = validator.validate_one(param, 5)
        assert result == 5

        with pytest.raises(ActionError, match="below minimum"):
            validator.validate_one(param, 0)

        with pytest.raises(ActionError, match="above maximum"):
            validator.validate_one(param, 11)

    def test_validate_min_length_max_length(self):
        """Test min_length/max_length  validation"""
        param = Param(
            name="name",
            type="str",
            validation=ValidationRule(min_length=2, max_length=5),
        )
        validator = Validator([param])

        result = validator.validate_one(param, "abc")
        assert result == "abc"

        with pytest.raises(ActionError, match="below minimum"):
            validator.validate_one(param, "a")

        with pytest.raises(ActionError, match="above maximum"):
            validator.validate_one(param, "abcdef")

    def test_validate_pattern(self):
        """Test pattern  validation"""
        param = Param(
            name="code",
            type="str",
            validation=ValidationRule(pattern=r"^\d{6}\.(SH|SZ)$"),
        )
        validator = Validator([param])

        result = validator.validate_one(param, "600000.SH")
        assert result == "600000.SH"

        with pytest.raises(ActionError, match="does not match pattern"):
            validator.validate_one(param, "invalid")

    def test_validate_custom(self):
        """Test  validation"""

        def validate_positive(value):
            if value <= 0:
                raise ValueError("must be positive")
            return value

        param = Param(
            name="count",
            type="int",
            validation=ValidationRule(custom="positive"),
        )
        validator = Validator([param])
        validator.register_custom("positive", validate_positive)

        result = validator.validate_one(param, 5)
        assert result == 5

        with pytest.raises(ActionError, match="custom validation failed"):
            validator.validate_one(param, -1)

    def test_validate_custom_not_registered(self):
        """Test  validationnot registered"""
        param = Param(
            name="count",
            type="int",
            validation=ValidationRule(custom="not_registered"),
        )
        validator = Validator([param])

        with pytest.raises(ActionError, match="not registered"):
            validator.validate_one(param, 5)

    def test_type_as_validation_rule(self):
        """Test type   ValidationRule"""
        rule = ValidationRule(pattern=r"^\d+$")
        param = Param(name="code", type=rule)
        validator = Validator([param])

        result = validator.validate_one(param, "12345")
        assert result == "12345"

        with pytest.raises(ActionError, match="does not match pattern"):
            validator.validate_one(param, "abc")

    def test_validate_none_not_required(self):
        """Test None  ( parameter) """
        param = Param(name="optional", type="str", required=False)
        validator = Validator([param])

        result = validator.validate_one(param, None)
        assert result is None

    def test_validate_none_required(self):
        """Test None  ( parameter) """
        param = Param(name="required", type="str", required=True)
        validator = Validator([param])

        # None for a required param is caught later; the validator itself does not reject it
        result = validator.validate_one(param, None)
        assert result is None


class TestCreateValidator:
    """Test create_validator """

    def test_create_validator(self):
        """Test  validation"""
        params = [Param(name="name", type="str")]
        validator = create_validator(params)

        assert isinstance(validator, Validator)
    
    def test_create_validator_with_custom(self):
        """Test  with  validation"""

        def validate(value):
            return value

        params = [Param(name="name", type="str")]
        validator = create_validator(
            params,
            custom_validators={"custom": validate},
        )

        assert "custom" in validator._custom_validators
        assert validator._custom_validators["custom"] is validate
