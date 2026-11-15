from django.core.exceptions import ValidationError
from django.db.models import Avg
from django.utils import timezone
from django.utils.translation import gettext as _

from ..models import FormDefinition, Review


def save_review(application, juror, score=None, note="") -> Review:
    """Create or update a juror's draft review."""
    _ensure_reviewable(application)
    value = _validate_score(score)

    review, _ = Review.objects.update_or_create(
        application=application,
        juror=juror,
        defaults={"score": value, "note": (note or "").strip()},
    )
    return review


def submit_review(application, juror, score=None, note="") -> Review:
    """Complete the review; a score is required, the note is optional."""
    if score in (None, ""):
        raise ValidationError(_("Enter a score before submitting your review."))

    review = save_review(application, juror, score=score, note=note)
    if review.completed_at is None:
        review.completed_at = timezone.now()
        review.save(update_fields=["completed_at", "updated_at"])
    return review


def review_stats(application, juror) -> dict:
    """Review data for one juror, respecting the blind rule."""
    reviews = application.reviews.select_related("juror")
    mine = reviews.filter(juror=juror).first()
    completed = reviews.filter(completed_at__isnull=False)

    is_blind = mine is None or mine.completed_at is None
    others = [] if is_blind else list(completed.exclude(juror=juror))
    average = None
    if not is_blind:
        average = completed.aggregate(average=Avg("score"))["average"]

    return {
        "my_review": mine,
        "other_reviews": others,
        "average_score": average,
        "completed_count": completed.count(),
        "is_blind": is_blind,
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
