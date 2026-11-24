"""Manage quizzes and questions without breaking complete quiz structure."""

from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from .models import Question, Quiz


class QuestionFormSet(BaseInlineFormSet):
    """Require all ten question slots when editing or adding a quiz."""

    def __init__(self, *args, **kwargs):
        """Enable Django's existing min/max count validation."""
        super().__init__(*args, **kwargs)
        self.min_num = self.max_num = 10
        self.validate_min = self.validate_max = True


class QuestionInline(admin.StackedInline):
    """Edit complete question sets together with their quiz."""

    model = Question
    formset = QuestionFormSet
    extra = 0
    min_num = max_num = 10
    can_delete = False
    readonly_fields = ("created_at", "updated_at")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    """Expose ownership, search, filters and inline question editing."""

    list_display = ("id", "title", "owner", "created_at")
    list_filter = ("created_at",)
    search_fields = ("title", "description", "owner__username")
    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (QuestionInline,)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """Allow individual question edits while preserving quiz membership and count."""

    list_display = ("id", "quiz", "position", "question_title")
    list_filter = ("quiz",)
    search_fields = ("question_title", "quiz__title")
    readonly_fields = ("quiz", "position", "created_at", "updated_at")

    def has_add_permission(self, request):
        """Add questions only through the complete quiz inline."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Delete questions only by deleting their containing quiz."""
        return False
