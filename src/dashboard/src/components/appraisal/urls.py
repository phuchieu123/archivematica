from django.conf.urls import url

from components.appraisal import views

app_name = "appraisal"
urlpatterns = [url(r"^$", views.appraisal, name="appraisal_index")]
