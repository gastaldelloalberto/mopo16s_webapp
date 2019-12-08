from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse


class PasswordResetMailTests(TestCase):
    def setUp(self):
        User.objects.create_user(username='paolo', email='paolo@posterdati.cc', password='sorellaLAbarella')
        self.response = self.client.post(reverse('password_reset'), {'email': 'paolo@posterdati.cc'})
        self.email = mail.outbox[0]
    
    def test_email_subject(self):
        self.assertEqual('[mopo16S Webapp] Please reset your password', self.email.subject)
    
    def test_email_body(self):
        context = self.response.context
        token = context.get('token')
        uid = context.get('uid')
        password_reset_token_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        self.assertIn(password_reset_token_url, self.email.body)
        self.assertIn('paolo', self.email.body)
        self.assertIn('paolo@posterdati.cc', self.email.body)
    
    def test_email_to(self):
        self.assertEqual(['paolo@posterdati.cc'], self.email.to)
