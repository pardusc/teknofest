from django.core.exceptions import ValidationError
from django.db.models import Avg
from django.utils import timezone
from django.utils.translation import gettext as _

from ..models import FormDefinition, Review


def submit_review(application, juror, score=None, note="") -> Review:
    """Submit the juror's review; a score is required, the note is optional."""
    if score in (None, ""):
        raise ValidationError(_("Enter a score before submitting your review."))

    _ensure_reviewable(application)
    value = _validate_score(score)

    review, created = Review.objects.get_or_create(
        application=application,
        juror=juror,
        defaults={
            "score": value,
            "note": (note or "").strip(),
            "completed_at": timezone.now(),
        },
    )
    if not created:
        review.score = value
        review.note = (note or "").strip()
        review.save(update_fields=["score", "note", "updated_at"])

    return review


def review_stats(application, juror) -> dict:
    """Review data for one juror. Other reviews are always visible."""
    reviews = application.reviews.select_related("juror")
    mine = reviews.filter(juror=juror).first()

    return {
        "my_review": mine,
        "other_reviews": list(reviews.exclude(juror=juror)),
        "average_score": reviews.aggregate(average=Avg("score"))["average"],
        "completed_count": reviews.count(),
    }


def _ensure_reviewable(application) -> None:
    if application.form.status != FormDefinition.Status.IN_REVIEW:
        raise ValidationError(
            _("Reviews can only be edited while the form is in review.")
        )


def _validate_score(score):
    if score in (None, ""):
        return None
    try:
        value = int(score)
    except (TypeError, ValueError) as exc:
        raise ValidationError(_("Enter a whole number between 0 and 100.")) from exc
    if not 0 <= value <= 100:
        raise ValidationError(_("Enter a whole number between 0 and 100."))
    return value
