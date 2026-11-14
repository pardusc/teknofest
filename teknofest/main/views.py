from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, UpdateView

from .dynamic_forms import build_form
from .forms import ProfileForm
from .models import FormDefinition, Profile


def home(request):
    return render(request, "main/home.html")


class ProfileView(LoginRequiredMixin, DetailView):
    model = Profile
    template_name = "main/profile_detail.html"
    context_object_name = "profile"

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = Profile
    form_class = ProfileForm
    template_name = "main/profile_edit.html"
    success_url = reverse_lazy("main:profile")

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Your profile has been updated.")
        return response


@staff_member_required
def form_preview(request, pk):
    definition = get_object_or_404(FormDefinition, pk=pk)
    return render(
        request,
        "main/form_preview.html",
        {"definition": definition, "form": build_form(definition)},
    )
