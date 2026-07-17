from django.contrib.auth.password_validation import (
    MinimumLengthValidator,
    UserAttributeSimilarityValidator,
    CommonPasswordValidator,
    NumericPasswordValidator,
)
from django.core.exceptions import ValidationError


class BgMinimumLengthValidator(MinimumLengthValidator):
    def validate(self, password, user=None):
        if len(password) < self.min_length:
            raise ValidationError(
                f'Паролата е твърде кратка. Трябва да съдържа поне {self.min_length} символа.',
                code='password_too_short',
            )

    def get_help_text(self):
        return f'Паролата трябва да съдържа поне {self.min_length} символа.'


class BgUserAttributeSimilarityValidator(UserAttributeSimilarityValidator):
    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError:
            raise ValidationError(
                'Паролата е твърде подобна на личните ви данни.',
                code='password_too_similar',
            )

    def get_help_text(self):
        return 'Паролата не трябва да е подобна на потребителското ви име или друга лична информация.'


class BgCommonPasswordValidator(CommonPasswordValidator):
    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError:
            raise ValidationError(
                'Паролата е твърде разпространена.',
                code='password_too_common',
            )

    def get_help_text(self):
        return 'Паролата не трябва да е широко използвана.'


class BgNumericPasswordValidator(NumericPasswordValidator):
    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError:
            raise ValidationError(
                'Паролата не може да се състои само от цифри.',
                code='password_entirely_numeric',
            )

    def get_help_text(self):
        return 'Паролата не може да се състои само от цифри.'
