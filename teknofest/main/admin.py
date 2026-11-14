from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm

from .models import Profile, User


class UserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
    fields = ("phone", "city", "institution", "education_level", "photo")
    readonly_fields = ("created_at", "updated_at")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    inlines = (ProfileInline,)
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Keycloak", {"fields": ("keycloak_id",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
    )
    list_display = ("username", "email", "first_name", "last_name", "is_staff")
    search_fields = ("username", "first_name", "last_name", "email", "keycloak_id")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "institution", "education_level", "updated_at")
    list_filter = ("education_level",)
    search_fields = ("user__username", "user__email", "city", "institution")
    readonly_fields = ("created_at", "updated_at")
