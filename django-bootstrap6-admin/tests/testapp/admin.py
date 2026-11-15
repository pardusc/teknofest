from django.contrib import admin

from .models import Author, Book, Chapter, Publisher, Tag


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "birth_date")
    search_fields = ("name", "email")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


class ChapterInline(admin.StackedInline):
    model = Chapter
    extra = 1
    fields = ("title", "order")


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "published", "is_active", "pages")
    list_display_links = ("title",)
    list_editable = ("is_active",)
    list_filter = ("is_active", "author", "tags")
    search_fields = ("title", "author__name")
    date_hierarchy = "published"
    autocomplete_fields = ("author",)
    raw_id_fields = ("publisher",)
    filter_horizontal = ("tags",)
    inlines = (ChapterInline,)
    actions = ("mark_inactive",)
    fieldsets = (
        (None, {"fields": ("title", "author", "tags")}),
        ("Publication", {"fields": ("publisher", "published", "pages", "is_active")}),
        ("Extra", {"classes": ("collapse",), "fields": ("summary",)}),
    )

    @admin.action(description="Mark selected books inactive")
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} book(s) marked inactive.")
