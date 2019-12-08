from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    def to_api_dict(self, include_private=False):
        d = dict(id=self.id, username=self.username, first_name=self.first_name)
        if include_private:
            d.update(last_name=self.last_name, email=self.email, is_active=self.is_active,
                     is_superuser=self.is_superuser, is_staff=self.is_staff)
        return d
    
    # uploaded_rep_set = reverse relation with RepresentativeSequenceSet
    # uploaded_good_pairs = reverse relation with InitialPrimerPairs


class ApiToken(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=256, blank=False, null=False)
    description = models.TextField(blank=False, null=False)
    token = models.SlugField(max_length=32, blank=False, null=False)
    owner = models.ForeignKey(User, on_delete=models.DO_NOTHING, related_name='apis', related_query_name='apis')
    
    class Meta:
        managed = False
        db_table = 'accounts_api_token'
