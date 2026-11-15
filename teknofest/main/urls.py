from django.urls import path

from . import views

app_name = "main"

urlpatterns = [
    path("", views.home, name="home"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/edit/", views.ProfileUpdateView.as_view(), name="profile_edit"),
    path("forms/", views.FormListView.as_view(), name="form_list"),
    path("forms/<int:pk>/", views.FormDetailView.as_view(), name="form_detail"),
    path(
        "forms/<int:pk>/apply/",
        views.ApplicationStartView.as_view(),
        name="application_start",
    ),
    path(
        "applications/",
        views.ApplicationListView.as_view(),
        name="application_list",
    ),
    path(
        "applications/<uuid:public_id>/",
        views.ApplicationDetailView.as_view(),
        name="application_detail",
    ),
    path(
        "applications/<uuid:public_id>/edit/",
        views.ApplicationUpdateView.as_view(),
        name="application_edit",
    ),
    path(
        "applications/<uuid:public_id>/preview/",
        views.ApplicationPreviewView.as_view(),
        name="application_preview",
    ),
    path(
        "applications/<uuid:public_id>/delete/",
        views.ApplicationDeleteView.as_view(),
        name="application_delete",
    ),
    path(
        "applications/<uuid:public_id>/attachments/upload/",
        views.AttachmentUploadView.as_view(),
        name="attachment_upload",
    ),
    path(
        "applications/<uuid:public_id>/attachments/<int:pk>/delete/",
        views.AttachmentDeleteView.as_view(),
        name="attachment_delete",
    ),
    path(
        "attachments/<int:pk>/thumbnail/",
        views.attachment_thumbnail,
        name="attachment_thumbnail",
    ),
    path(
        "attachments/<int:pk>/preview/",
        views.attachment_preview,
        name="attachment_preview",
    ),
    path(
        "attachments/<int:pk>/download/",
        views.attachment_download,
        name="attachment_download",
    ),
    path("jury/", views.JuryDashboardView.as_view(), name="jury_dashboard"),
    path(
        "jury/api-keys/",
        views.JuryAPIKeyListView.as_view(),
        name="jury_api_keys",
    ),
    path(
        "jury/api-keys/<int:pk>/revoke/",
        views.JuryAPIKeyRevokeView.as_view(),
        name="jury_api_key_revoke",
    ),
    path(
        "jury/forms/<int:pk>/",
        views.JuryApplicationListView.as_view(),
        name="jury_application_list",
    ),
    path(
        "jury/applications/<uuid:public_id>/",
        views.JuryApplicationDetailView.as_view(),
        name="jury_application_detail",
    ),
    path(
        "jury/applications/<uuid:public_id>/review/submit/",
        views.JuryReviewSubmitView.as_view(),
        name="jury_review_submit",
    ),
    path("staff/forms/<int:pk>/preview/", views.form_preview, name="form_preview"),
    path("media/<path:path>", views.protected_media, name="protected_media"),
]
