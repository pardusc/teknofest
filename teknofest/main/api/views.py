from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Application, Attachment, FormDefinition, FormField
from ..services import reviews as review_service
from ..services.jury import (
    REVIEWABLE_APPLICATION_STATUSES,
    jury_application_queryset,
    jury_form_queryset,
)
from ..services.reviews import review_stats
from .serializers import ReviewInputSerializer


def _iso(value):
    return value.isoformat() if value else None


def _category_data(category):
    return {
        "id": category.pk,
        "slug": category.slug,
        "name": category.display_name,
    }


def _form_data(form):
    return {
        "id": form.pk,
        "title": form.title,
        "year": form.year.year,
        "category": _category_data(form.category),
        "status": form.status,
        "application_count": getattr(form, "application_count", None),
        "my_completed_count": getattr(form, "my_completed_count", None),
        "opens_at": _iso(form.opens_at),
        "closes_at": _iso(form.closes_at),
    }


def _application_data(application):
    return {
        "public_id": str(application.public_id),
        "code": application.code,
        "status": application.status,
        "submitted_at": _iso(application.submitted_at),
        "updated_at": _iso(application.updated_at),
        "category": _category_data(application.category),
        "attachment_count": getattr(application, "attachment_count", None),
        "my_score": getattr(application, "my_score", None),
        "my_completed": getattr(application, "my_completed", None),
        "average": getattr(application, "average", None),
    }


def _answers_data(application):
    fields = application.form.fields.filter(
        review_visibility__in=[
            FormField.ReviewVisibility.VISIBLE,
            FormField.ReviewVisibility.MASKED,
        ]
    )
    answers = {
        answer.field_id: answer.value
        for answer in application.answers.filter(
            field__review_visibility=FormField.ReviewVisibility.VISIBLE
        )
    }
    items = []
    for field in fields:
        masked = field.review_visibility == FormField.ReviewVisibility.MASKED
        items.append(
            {
                "key": field.key,
                "label": field.label,
                "field_type": field.field_type,
                "masked": masked,
                "value": None if masked else answers.get(field.pk, ""),
            }
        )
    return items


def _attachments_data(application, request):
    return [
        {
            "id": attachment.pk,
            "name": attachment.original_name,
            "content_type": attachment.content_type,
            "size": attachment.size,
            "download_url": request.build_absolute_uri(
                reverse(
                    "jury_api_attachment",
                    args=[application.public_id, attachment.pk],
                )
            ),
        }
        for attachment in application.attachments.all()
    ]


def _review_data(review):
    if review is None:
        return None
    return {
        "id": review.pk,
        "score": review.score,
        "note": review.note,
        "completed_at": _iso(review.completed_at),
        "updated_at": _iso(review.updated_at),
    }


def _other_review_data(review):
    return {
        **_review_data(review),
        "juror_name": review.juror_name,
    }


def _applicant_data(application):
    masked = application.form.mask_applicant_identity
    if masked:
        return {"masked": True, "name": None, "email": None}
    applicant = application.applicant
    return {
        "masked": False,
        "name": applicant.get_full_name() or applicant.username,
        "email": applicant.email,
    }


def _application_detail_data(application, request):
    stats = review_stats(application, request.user)
    my_review = stats["my_review"]
    application_data = _application_data(application)
    application_data.update(
        {
            "attachment_count": application.attachments.count(),
            "my_score": my_review.score if my_review else None,
            "my_completed": my_review is not None,
            "average": stats["average_score"],
        }
    )
    return {
        "application": application_data,
        "form": {
            "id": application.form.pk,
            "title": application.form.title,
            "year": application.year.year,
            "category": _category_data(application.category),
            "status": application.form.status,
        },
        "applicant": _applicant_data(application),
        "answers": _answers_data(application),
        "attachments": _attachments_data(application, request),
        "can_review": application.form.status == FormDefinition.Status.IN_REVIEW,
        "my_review": _review_data(my_review),
        "other_reviews": [
            _other_review_data(review) for review in stats["other_reviews"]
        ],
        "average_score": stats["average_score"],
        "completed_count": stats["completed_count"],
    }


class JuryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class JuryFormListView(APIView):
    def get(self, request):
        forms = jury_form_queryset(request.user)
        return Response([_form_data(form) for form in forms])


class JuryApplicationListView(APIView):
    pagination_class = JuryPagination

    def get(self, request, pk):
        form_definition = get_object_or_404(
            FormDefinition.objects.select_related("year", "category"),
            pk=pk,
        )
        queryset = jury_application_queryset(
            form_definition,
            request.user,
            request.query_params,
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        results = [_application_data(application) for application in page]
        return paginator.get_paginated_response(results)


class JuryApplicationDetailView(APIView):
    def get(self, request, public_id):
        application = _get_application(public_id)
        return Response(_application_detail_data(application, request))


class JuryReviewSubmitView(APIView):
    def post(self, request, public_id):
        application = _get_application(public_id)
        serializer = ReviewInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            review = review_service.submit_review(
                application,
                request.user,
                score=serializer.validated_data["score"],
                note=serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stats = review_stats(application, request.user)
        return Response(
            {
                "review": _review_data(review),
                "average_score": stats["average_score"],
                "completed_count": stats["completed_count"],
            }
        )


class JuryAttachmentDownloadView(APIView):
    def get(self, request, public_id, pk):
        attachment = get_object_or_404(
            Attachment.objects.select_related("application").filter(
                application__public_id=public_id,
                application__status__in=REVIEWABLE_APPLICATION_STATUSES,
            ),
            pk=pk,
        )
        try:
            response = FileResponse(
                attachment.file.open("rb"),
                content_type=attachment.content_type or "application/octet-stream",
                filename=attachment.original_name,
            )
        except FileNotFoundError as exc:
            raise Http404 from exc
        response["X-Content-Type-Options"] = "nosniff"
        return response


class JuryMeView(APIView):
    def get(self, request):
        key = request.auth
        user = request.user
        return Response(
            {
                "user": {
                    "id": user.pk,
                    "username": user.username,
                    "name": user.get_full_name() or user.username,
                    "email": user.email,
                },
                "api_key": {
                    "id": key.pk,
                    "name": key.name,
                    "prefix": key.prefix,
                    "created_at": _iso(key.created_at),
                    "expires_at": _iso(key.expires_at),
                    "last_used_at": _iso(key.last_used_at),
                },
            }
        )


def _get_application(public_id):
    return get_object_or_404(
        Application.objects.select_related(
            "form",
            "year",
            "category",
            "applicant",
        ).filter(status__in=REVIEWABLE_APPLICATION_STATUSES),
        public_id=public_id,
    )
