from django import template

register = template.Library()

@register.filter(name='get_slot')
def get_slot(dictionary, key):
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.simple_tag
def is_room_busy_tag(occupied_dict, day, ts_id, room_id, slot_id, stream_id, week_type):
    try:
        if not occupied_dict:
            return False
            
        occupants = occupied_dict.get(day, {}).get(ts_id, {}).get(room_id,[])
        if not occupants:
            return False

        str_slot_id = str(slot_id)
        str_stream_id = str(stream_id) if stream_id else 'None'

        for occ in occupants:
            if occ['slot_id'] == str_slot_id:
                continue
            if str_stream_id != 'None' and occ['stream_id'] == str_stream_id:
                continue
            
            occ_wt = occ.get('week_type', 'EVERY')
            if week_type == 'EVERY' or occ_wt == 'EVERY' or week_type == occ_wt:
                return True 

        return False
    except Exception as e:
        print(f"Tag error: {e}")
        return False