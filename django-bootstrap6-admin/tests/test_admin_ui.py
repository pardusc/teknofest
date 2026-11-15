from datetime import date

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .testapp.models import Author, Book, Chapter, Tag


class AdminUiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        cls.author = Author.objects.create(
            name="Ada Lovelace",
            email="ada@example.com",
            birth_date=date(1815, 12, 10),
        )
        cls.tag = Tag.objects.create(name="python")
        cls.book = Book.objects.create(
            title="Django for Everyone",
            author=cls.author,
            published=date(2026, 1, 15),
            pages=320,
            summary="A test book.",
        )
        cls.book.tags.add(cls.tag)
        Chapter.objects.create(book=cls.book, title="Getting started", order=1)

    def setUp(self):
        self.client.force_login(self.user)

    def test_dashboard_is_bootstrap_based(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/index.html")
        self.assertContains(
            response, "django_bootstrap6_admin/vendor/bootstrap/css/bootstrap.min.css"
        )
        self.assertContains(response, "django_bootstrap6_admin/css/admin.css")
        self.assertContains(response, "ba-topbar")
        self.assertContains(response, "ba-app-grid")
        self.assertContains(response, "ba-recent-card")
        self.assertContains(response, "theme-toggle")

    def test_default_django_admin_css_is_not_loaded(self):
        response = self.client.get(reverse("admin:index"))

        self.assertNotContains(response, "admin/css/base.css")
        self.assertNotContains(response, "admin/css/dashboard.css")
        self.assertNotContains(response, "admin/css/changelists.css")

    def test_app_index_uses_cards(self):
        response = self.client.get(reverse("admin:app_list", args=["testapp"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ba-app-card")
        self.assertContains(response, "testapp")
        self.assertContains(response, "Book")

    def test_changelist_keeps_django_javascript_contract(self):
        response = self.client.get(reverse("admin:testapp_book_changelist"))

        self.assertEqual(response.status_code, 200)
        for marker in (
            'id="changelist"',
            'id="changelist-form"',
            'id="result_list"',
            'id="changelist-search"',
            'id="searchbar"',
            'id="changelist-filter"',
            'id="action-toggle"',
            'id="date-hierarchy-label"',
            'class="actions ba-actions"',
            "action-counter",
            'name="select_across"',
            'name="index"',
            "data-filter-title=",
            "ba-table-wrap",
        ):
            self.assertContains(response, marker)

        self.assertContains(response, "aria-sort=")
        self.assertContains(response, "name=\"form-0-is_active\"")

    def test_user_content_is_escaped(self):
        Book.objects.create(
            title="<script>alert(1)</script>",
            author=self.author,
            published=date(2026, 3, 1),
            pages=1,
        )

        response = self.client.get(reverse("admin:testapp_book_changelist"))

        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_post_forms_include_csrf_tokens(self):
        self.client.logout()
        self.assertContains(
            self.client.get(reverse("admin:login")), "csrfmiddlewaretoken"
        )
        self.client.force_login(self.user)
        self.assertContains(
            self.client.get(
                reverse("admin:testapp_book_change", args=[self.book.pk])
            ),
            "csrfmiddlewaretoken",
        )
        self.assertContains(
            self.client.get(
                reverse("admin:testapp_book_delete", args=[self.book.pk])
            ),
            "csrfmiddlewaretoken",
        )

    def test_changelist_search_and_pagination(self):
        response = self.client.get(
            reverse("admin:testapp_book_changelist"), {"q": "Django"}
        )
        self.assertContains(response, "Django for Everyone")

        for index in range(105):
            Book.objects.create(
                title=f"Extra book {index:03d}",
                author=self.author,
                published=date(2026, 2, 1),
                pages=10,
            )

        response = self.client.get(
            reverse("admin:testapp_book_changelist"), {"p": "2"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "class=\"pagination")
        self.assertContains(response, "?p=1")
        self.assertContains(response, 'aria-current="page">2')

    def test_change_form_keeps_widgets_and_submit_contract(self):
        response = self.client.get(
            reverse("admin:testapp_book_change", args=[self.book.pk])
        )

        self.assertEqual(response.status_code, 200)
        for marker in (
            'id="book_form"',
            'id="django-admin-form-add-constants"',
            'name="_save"',
            'name="_continue"',
            "related-widget-wrapper",
            'id="add_id_author"',
            "admin-autocomplete",
            "selectfilter",
            "related-lookup",
            'id="lookup_id_publisher"',
            "ba-collapse",
            "ba-submit-row",
            "deletelink",
            "historylink",
        ):
            self.assertContains(response, marker)

        self.assertContains(response, "data-inline-type=\"stacked\"")
        self.assertContains(response, "chapters-group")
        self.assertContains(response, "empty-form")

    def test_bulk_action_still_works(self):
        url = reverse("admin:testapp_book_changelist")
        response = self.client.post(
            url,
            {
                "action": "mark_inactive",
                "_selected_action": [str(self.book.pk)],
                "select_across": "0",
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.book.refresh_from_db()
        self.assertFalse(self.book.is_active)

    def test_delete_confirmation_and_delete(self):
        url = reverse("admin:testapp_book_delete", args=[self.book.pk])
        response = self.client.get(url)

        self.assertContains(response, 'name="post" value="yes"')
        self.assertContains(response, "cancel-link")
        self.assertContains(response, "ba-confirm-card")

        response = self.client.post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Book.objects.filter(pk=self.book.pk).exists())

    def test_object_history_renders(self):
        LogEntry.objects.log_actions(
            user_id=self.user.pk,
            queryset=[self.book],
            action_flag=CHANGE,
            change_message="Changed for the UI test.",
            single_object=True,
        )

        response = self.client.get(
            reverse("admin:testapp_book_history", args=[self.book.pk])
        )

        self.assertContains(response, 'id="change-history"')
        self.assertContains(response, "ba-history-table")

    def test_login_page(self):
        self.client.logout()
        response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="login-form"')
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'type="password"')
        self.assertContains(response, "theme-toggle")
        self.assertContains(response, "ba-login")

    def test_login_post_works(self):
        self.client.logout()
        response = self.client.post(
            reverse("admin:login"),
            {
                "username": "admin",
                "password": "password",
                "next": reverse("admin:index"),
            },
        )

        self.assertRedirects(response, reverse("admin:index"))

    def test_password_change_page(self):
        response = self.client.get(reverse("admin:password_change"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ba-password-card")
        self.assertContains(response, 'name="old_password"')
        self.assertContains(response, 'name="new_password1"')
        self.assertContains(response, 'name="new_password2"')

    def test_password_change_post(self):
        response = self.client.post(
            reverse("admin:password_change"),
            {
                "old_password": "password",
                "new_password1": "New-password-12345",
                "new_password2": "New-password-12345",
            },
        )

        self.assertRedirects(response, reverse("admin:password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-password-12345"))

    def test_admin_user_password_page(self):
        response = self.client.get(
            reverse("admin:auth_user_password_change", args=[self.user.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="user_form"')
        self.assertContains(response, 'name="usable_password"')
        self.assertContains(response, 'name="password1"')
        self.assertContains(response, 'name="password2"')
        self.assertContains(response, 'name="set-password"')

    def test_popup_change_form_has_no_shell(self):
        response = self.client.get(
            reverse("admin:testapp_book_add"), {"_popup": "1"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="book_form"')
        self.assertNotContains(response, 'id="header"')
        self.assertNotContains(response, "ba-sidebar")

    def test_theme_assets_and_attributes(self):
        response = self.client.get(reverse("admin:index"))

        self.assertContains(response, "django_bootstrap6_admin/js/theme.js")
        self.assertContains(response, "data-label-auto=")
        self.assertContains(response, "theme-icon-when-dark")
