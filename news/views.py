from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from .models import News, NewsComment
from .forms import NewsForm, NewsCommentForm

def is_dean(user):
    return user.is_authenticated and user.role == 'DEAN'


@login_required
def news_list(request):
    """Список всех новостей"""
    category = request.GET.get('category', '')
    
    news_queryset = News.objects.filter(is_published=True)
    
    if category:
        news_queryset = news_queryset.filter(category=category)
    
    # Пагинация
    paginator = Paginator(news_queryset, 10)
    page_number = request.GET.get('page')
    news_page = paginator.get_page(page_number)
    
    categories = News.CATEGORY_CHOICES
    
    return render(request, 'news/news_list.html', {
        'news_page': news_page,
        'categories': categories,
        'selected_category': category,
    })


@login_required
def news_detail(request, news_id):
    """Детальный просмотр новости"""
    news = get_object_or_404(News, id=news_id, is_published=True)
    news.increment_views()
    
    comments = news.comments.select_related('author').order_by('-created_at')
    
    if request.method == 'POST':
        form = NewsCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.news = news
            comment.author = request.user
            comment.save()
            messages.success(request, 'Комментарий добавлен')
            return redirect('news:detail', news_id=news_id)
    else:
        form = NewsCommentForm()
    
    return render(request, 'news/news_detail.html', {
        'news': news,
        'comments': comments,
        'form': form,
    })


@user_passes_test(is_dean)
def news_create(request):
    """Создание новости (только декан)"""
    if request.method == 'POST':
        form = NewsForm(request.POST, request.FILES)
        if form.is_valid():
            news = form.save(commit=False)
            news.author = request.user
            news.save()
            messages.success(request, 'Новость успешно создана')
            return redirect('news:detail', news_id=news.id)
    else:
        form = NewsForm()
    
    return render(request, 'news/news_form.html', {
        'form': form,
        'title': 'Создать новость'
    })


@user_passes_test(is_dean)
def news_edit(request, news_id):
    """Редактирование новости (только декан)"""
    news = get_object_or_404(News, id=news_id)
    
    if request.method == 'POST':
        form = NewsForm(request.POST, request.FILES, instance=news)
        if form.is_valid():
            form.save()
            messages.success(request, 'Новость обновлена')
            return redirect('news:detail', news_id=news_id)
    else:
        form = NewsForm(instance=news)
    
    return render(request, 'news/news_form.html', {
        'form': form,
        'title': 'Редактировать новость',
        'news': news
    })


@user_passes_test(is_dean)
def news_delete(request, news_id):
    """Удаление новости (только декан)"""
    news = get_object_or_404(News, id=news_id)
    news.delete()
    messages.success(request, 'Новость удалена')
    return redirect('news:list')


@user_passes_test(is_dean)
def news_toggle_publish(request, news_id):
    """Публикация/снятие с публикации"""
    news = get_object_or_404(News, id=news_id)
    news.is_published = not news.is_published
    news.save()
    
    status = "опубликована" if news.is_published else "снята с публикации"
    messages.success(request, f'Новость {status}')
    return redirect('news:detail', news_id=news_id)


@user_passes_test(is_dean)
def news_toggle_pin(request, news_id):
    """Закрепление/открепление новости"""
    news = get_object_or_404(News, id=news_id)
    news.is_pinned = not news.is_pinned
    news.save()
    
    status = "закреплена" if news.is_pinned else "откреплена"
    messages.success(request, f'Новость {status}')
    return redirect('news:detail', news_id=news_id)