"""apps/core/tests.py - Unit tests for core models and Community Feed suite."""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.core.models import (
    CommunityProfile,
    CommunityPost,
    CommunityComment,
    CommunityLike,
    CommunityFollow,
)


class CommunityFeedTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='investor1', password='Password123!', email='inv1@example.com')
        self.user2 = User.objects.create_user(username='investor2', password='Password123!', email='inv2@example.com')

    def test_community_page_login_required(self):
        url = reverse('core:learn_community')
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/accounts/login/', res.url)

    def test_community_page_logged_in(self):
        self.client.login(username='investor1', password='Password123!')
        url = reverse('core:learn_community')
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Investor Community Feed')
        self.assertTrue(CommunityProfile.objects.filter(user=self.user1).exists())

    def test_create_post_and_like(self):
        self.client.login(username='investor1', password='Password123!')
        
        # 1. Create post
        create_url = reverse('core:community_create_post_api')
        res = self.client.post(create_url, {
            'title': 'Index vs Active Analysis',
            'content': 'Comparing rolling Sharpe ratios of large-cap active vs passive funds over 10 years.',
            'tags': '#IndexFunds #Alpha #Strategy'
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        post_id = data['post_id']

        post = CommunityPost.objects.get(id=post_id)
        self.assertEqual(post.title, 'Index vs Active Analysis')
        self.assertEqual(post.tag_list(), ['IndexFunds', 'Alpha', 'Strategy'])

        # 2. Like post (as user2)
        self.client.login(username='investor2', password='Password123!')
        like_url = reverse('core:community_like_api', kwargs={'post_id': post_id})
        res = self.client.post(like_url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['liked'])
        self.assertEqual(res.json()['likes_count'], 1)

        # Unlike
        res = self.client.post(like_url)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['liked'])
        self.assertEqual(res.json()['likes_count'], 0)

    def test_reply_to_post(self):
        post = CommunityPost.objects.create(
            author=self.user1,
            title='Sample Thread',
            content='Testing discussions'
        )
        self.client.login(username='investor2', password='Password123!')
        reply_url = reverse('core:community_reply_api', kwargs={'post_id': post.id})
        res = self.client.post(reply_url, {'content': 'Great insights!'})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['replies_count'], 1)
        self.assertEqual(data['reply']['content'], 'Great insights!')
        self.assertEqual(CommunityComment.objects.filter(post=post).count(), 1)

    def test_follow_and_following_feed(self):
        # User 2 creates a post
        p = CommunityPost.objects.create(
            author=self.user2,
            title='User 2 Post',
            content='Content by user 2'
        )

        self.client.login(username='investor1', password='Password123!')
        
        # Follow user 2
        follow_url = reverse('core:community_follow_api', kwargs={'user_id': self.user2.id})
        res = self.client.post(follow_url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['is_following'])

        # Verify Following Feed shows user 2's post
        feed_url = reverse('core:learn_community') + '?tab=following'
        res = self.client.get(feed_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'User 2 Post')

        # Cannot follow self
        self_follow_url = reverse('core:community_follow_api', kwargs={'user_id': self.user1.id})
        res = self.client.post(self_follow_url)
        self.assertEqual(res.status_code, 400)

    def test_profile_api_and_update(self):
        self.client.login(username='investor1', password='Password123!')
        
        # Update profile
        update_url = reverse('core:community_update_my_profile_api')
        res = self.client.post(update_url, {
            'display_name': 'Aman Investor',
            'bio': 'Disciplined SIP investor.',
            'investor_tag': 'Quant Researcher',
            'avatar_color': 'av-violet',
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])

        profile = CommunityProfile.objects.get(user=self.user1)
        self.assertEqual(profile.display_name, 'Aman Investor')
        self.assertEqual(profile.investor_tag, 'Quant Researcher')
        self.assertEqual(profile.avatar_color, 'av-violet')

        # Get profile JSON
        profile_url = reverse('core:community_user_profile_api', kwargs={'user_id': self.user1.id})
        res = self.client.get(profile_url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['user']['display_name'], 'Aman Investor')
        self.assertEqual(data['user']['investor_tag'], 'Quant Researcher')

    def test_network_api_and_tag_filter(self):
        CommunityFollow.objects.create(follower=self.user1, following=self.user2)
        self.client.login(username='investor1', password='Password123!')

        # Followers of user2
        net_url = reverse('core:community_user_network_api', kwargs={'user_id': self.user2.id}) + '?type=followers'
        res = self.client.get(net_url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertEqual(len(res.json()['users']), 1)
        self.assertEqual(res.json()['users'][0]['username'], 'investor1')

        # Tag filter on community page
        CommunityPost.objects.create(
            author=self.user2,
            title='Tax Planning Post',
            content='ELSS vs PPF analysis',
            tags='TaxPlanning, ELSS'
        )
        tag_page_url = reverse('core:learn_community') + '?tag=TaxPlanning'
        res = self.client.get(tag_page_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Tax Planning Post')

