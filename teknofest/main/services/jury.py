from django.db.models import Avg, Count, Exists, FloatField, OuterRef, Q, Subquery
from django.db.models import QuerySet

from ..models import Application, FormDefinition, Review

REVIEWABLE_APPLICATION_STATUSES = (
    Application.Status.SUBMITTED,
    Application.Status.IN_REVIEW,
    Application.Status.EVALUATED,
)

REVIEW_ORDERING = {
    "submitted_at",
    "-submitted_at",
    "my_score",
    "-my_score",
    "average",
    "-average",
}


def jury_form_queryset(user) -> QuerySet[FormDefinition]:
    """Forms shown on the jury dashboard, with counts for the current juror."""
    return (
        FormDefinition.objects.select_related("year", "category")
        .filter(year__is_active=True, category__is_active=True)
        .annotate(
            application_count=Count(
                "applications",
                filter=Q(
                    applications__status__in=REVIEWABLE_APPLICATION_STATUSES
                ),
                distinct=True,
            ),
            my_completed_count=Count(
                "applications__reviews",
                filter=Q(
                    applications__reviews__juror=user,
                    applications__reviews__completed_at__isnull=False,
                ),
                distinct=True,
            ),
        )
        .order_by("-year__year", "category__order")
    )


def jury_application_queryset(form_definition, user, params) -> QuerySet[Application]:
    """Applications for one form, with the same filters as the jury UI."""
    my_reviews = Review.objects.filter(
        application=OuterRef("pk"),
        juror=user,
    )
    average_reviews = (
        Review.objects.filter(application=OuterRef("pk"))
        .values("application")
        .annotate(value=Avg("score"))
        .values("value")
    )

    queryset = (
        Application.objects.select_related("form", "year", "category")
        .filter(
            form=form_definition,
            status__in=REVIEWABLE_APPLICATION_STATUSES,
        )
        .annotate(
            my_score=Subquery(my_reviews.values("score")[:1]),
            my_completed=Exists(my_reviews),
            average=Subquery(average_reviews, output_field=FloatField()),
            attachment_count=Count("attachments", distinct=True),
        )
    )

    mine = params.get("mine")
    if mine == "completed":
        queryset = queryset.filter(my_completed=True)
    elif mine == "pending":
        queryset = queryset.filter(my_completed=False)

    query = params.get("q", "").strip()
    if query:
        conditions = Q(code__icontains=query) | Q(title__icontains=query)
        if not form_definition.mask_applicant_identity:
            conditions |= Q(applicant__email__icontains=query)
        queryset = queryset.filter(conditions)

    ordering = params.get("ordering", "-submitted_at")
    if ordering not in REVIEW_ORDERING:
        ordering = "-submitted_at"
    return queryset.order_by(ordering, "pk")


def jury_application_queue(form_definition, user, params) -> list:
    return list(
        jury_application_queryset(form_definition, user, params)
        .values_list("public_id", flat=True)
        .distinct()
    )
