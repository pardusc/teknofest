from django.urls import path

from . import views

urlpatterns = [
    path("jury/forms/", views.JuryFormListView.as_view(), name="jury_api_forms"),
    path(
        "jury/forms/<int:pk>/applications/",
        views.JuryApplicationListView.as_view(),
        name="jury_api_applications",
    ),
    path(
        "jury/applications/<uuid:public_id>/",
        views.JuryApplicationDetailView.as_view(),
        name="jury_api_application",
    ),
    path(
        "jury/applications/<uuid:public_id>/review/",
        views.JuryReviewSubmitView.as_view(),
        name="jury_api_review",
    ),
    path(
        "jury/applications/<uuid:public_id>/attachments/<int:pk>/download/",
        views.JuryAttachmentDownloadView.as_view(),
        name="jury_api_attachment",
    ),
    path("jury/me/", views.JuryMeView.as_view(), name="jury_api_me"),
]
