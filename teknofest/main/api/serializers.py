from rest_framework import serializers


class ReviewInputSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=0, max_value=100)
    note = serializers.CharField(required=False, allow_blank=True)
