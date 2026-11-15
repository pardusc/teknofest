from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    birth_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Publisher(models.Model):
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=160)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="books")
    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.SET_NULL,
        related_name="books",
        null=True,
        blank=True,
    )
    tags = models.ManyToManyField(Tag, blank=True)
    published = models.DateField(null=True, blank=True)
    pages = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ("title",)

    def __str__(self):
        return self.title


class Chapter(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="chapters")
    title = models.CharField(max_length=160)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "title")

    def __str__(self):
        return self.title
