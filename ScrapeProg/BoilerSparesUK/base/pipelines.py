from itemadapter import ItemAdapter

class BasePipeline:
    def process_item(self, item, spider):
        return item
