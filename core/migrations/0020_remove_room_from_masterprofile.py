from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_add_room_to_service"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="masterprofile",
            name="room",
        ),
    ]

