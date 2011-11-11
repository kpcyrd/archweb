from datetime import datetime

from django import forms
from django.contrib.admin.widgets import AdminDateWidget
from django.contrib.auth.models import User
from django.db.models import Q
from django.views.generic import list_detail

from main.models import Package, Arch, Repo
from main.utils import make_choice
from ..models import PackageRelation


def coerce_limit_value(value):
    if not value:
        return None
    if value == 'all':
        # negative value indicates show all results
        return -1
    value = int(value)
    if value < 0:
        raise ValueError
    return value

class LimitTypedChoiceField(forms.TypedChoiceField):
    def valid_value(self, value):
        try:
            coerce_limit_value(value)
            return True
        except (ValueError, TypeError):
            return False

class PackageSearchForm(forms.Form):
    repo = forms.MultipleChoiceField(required=False)
    arch = forms.MultipleChoiceField(required=False)
    name = forms.CharField(required=False)
    desc = forms.CharField(required=False)
    q = forms.CharField(required=False)
    maintainer = forms.ChoiceField(required=False)
    packager = forms.ChoiceField(required=False)
    last_update = forms.DateField(required=False, widget=AdminDateWidget(),
            label='Last Updated After')
    flagged = forms.ChoiceField(
            choices=[('', 'All')] + make_choice(['Flagged', 'Not Flagged']),
            required=False)
    signed = forms.ChoiceField(
            choices=[('', 'All')] + make_choice(['Signed', 'Unsigned']),
            required=False)
    limit = LimitTypedChoiceField(
            choices=make_choice([50, 100, 250]) + [('all', 'All')],
            coerce=coerce_limit_value,
            required=False,
            initial=50)

    def __init__(self, *args, **kwargs):
        super(PackageSearchForm, self).__init__(*args, **kwargs)
        self.fields['repo'].choices = make_choice(
                        [repo.name for repo in Repo.objects.all()])
        self.fields['arch'].choices = make_choice(
                        [arch.name for arch in Arch.objects.all()])
        self.fields['q'].widget.attrs.update({"size": "30"})
        maints = User.objects.filter(is_active=True).order_by('username')
        self.fields['maintainer'].choices = \
                [('', 'All'), ('orphan', 'Orphan')] + \
                [(m.username, m.get_full_name()) for m in maints]
        self.fields['packager'].choices = \
                [('', 'All'), ('unknown', 'Unknown')] + \
                [(m.username, m.get_full_name()) for m in maints]

def search(request, page=None):
    limit = 50
    packages = Package.objects.normal()

    if request.GET:
        form = PackageSearchForm(data=request.GET)
        if form.is_valid():
            if form.cleaned_data['repo']:
                packages = packages.filter(
                        repo__name__in=form.cleaned_data['repo'])

            if form.cleaned_data['arch']:
                packages = packages.filter(
                        arch__name__in=form.cleaned_data['arch'])

            if form.cleaned_data['maintainer'] == 'orphan':
                inner_q = PackageRelation.objects.all().values('pkgbase')
                packages = packages.exclude(pkgbase__in=inner_q)
            elif form.cleaned_data['maintainer']:
                inner_q = PackageRelation.objects.filter(
                        user__username=form.cleaned_data['maintainer']).values('pkgbase')
                packages = packages.filter(pkgbase__in=inner_q)

            if form.cleaned_data['packager'] == 'unknown':
                packages = packages.filter(packager__isnull=True)
            elif form.cleaned_data['packager']:
                packages = packages.filter(
                        packager__username=form.cleaned_data['packager'])

            if form.cleaned_data['flagged'] == 'Flagged':
                packages = packages.filter(flag_date__isnull=False)
            elif form.cleaned_data['flagged'] == 'Not Flagged':
                packages = packages.filter(flag_date__isnull=True)

            if form.cleaned_data['signed'] == 'Signed':
                packages = packages.filter(pgp_signature__isnull=False)
            elif form.cleaned_data['signed'] == 'Unsigned':
                packages = packages.filter(pgp_signature__isnull=True)

            if form.cleaned_data['last_update']:
                lu = form.cleaned_data['last_update']
                packages = packages.filter(last_update__gte=
                        datetime(lu.year, lu.month, lu.day, 0, 0))

            if form.cleaned_data['name']:
                name = form.cleaned_data['name']
                packages = packages.filter(pkgname__icontains=name)

            if form.cleaned_data['desc']:
                desc = form.cleaned_data['desc']
                packages = packages.filter(pkgdesc__icontains=desc)

            if form.cleaned_data['q']:
                query = form.cleaned_data['q']
                q = Q(pkgname__icontains=query) | Q(pkgdesc__icontains=query)
                packages = packages.filter(q)

            asked_limit = form.cleaned_data['limit']
            if asked_limit and asked_limit < 0:
                limit = None
            elif asked_limit:
                limit = asked_limit
        else:
            # Form had errors, don't return any results, just the busted form
            packages = Package.objects.none()
    else:
        form = PackageSearchForm()

    current_query = request.GET.urlencode()
    page_dict = {
            'search_form': form,
            'current_query': current_query
    }
    allowed_sort = ["arch", "repo", "pkgname", "pkgbase",
            "compressed_size", "installed_size",
            "build_date", "last_update", "flag_date"]
    allowed_sort += ["-" + s for s in allowed_sort]
    sort = request.GET.get('sort', None)
    if sort in allowed_sort:
        packages = packages.order_by(sort)
        page_dict['sort'] = sort
    else:
        packages = packages.order_by('pkgname')

    return list_detail.object_list(request, packages,
            template_name="packages/search.html",
            page=page,
            paginate_by=limit,
            template_object_name="package",
            extra_context=page_dict)

# vim: set ts=4 sw=4 et:
