#import "QRURLViewController.h"
#import "AppDelegate.h"
#import "URLEntity.h"
#import "NSString+Tools.h"
#import "QRPhoneResultViewController.h"
@interface QRURLViewController () <UITableViewDataSource, UITableViewDelegate, NSFetchedResultsControllerDelegate>
@property (nonatomic, strong) UITableView *tableView;
@property (nonatomic, strong) UILabel *emptyLabel;
@property (nonatomic, strong) NSFetchedResultsController *fetchedResultsController;
@end
@implementation QRURLViewController
- (void)loadView {
    self.tableView = [[UITableView alloc] initWithFrame:CGRectZero style:UITableViewStylePlain];
    self.tableView.accessibilityIdentifier = @"history.table";
    self.tableView.rowHeight = UITableViewAutomaticDimension;
    self.tableView.estimatedRowHeight = 70;
    self.tableView.dataSource = self; self.tableView.delegate = self;
    [self.tableView registerClass:UITableViewCell.class forCellReuseIdentifier:@"urlCell"];
    self.tableView.tableFooterView = [UIView new];
    self.emptyLabel = [UILabel new];
    self.emptyLabel.numberOfLines = 0;
    self.emptyLabel.textAlignment = NSTextAlignmentCenter;
    self.emptyLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    self.emptyLabel.adjustsFontForContentSizeCategory = YES;
    self.emptyLabel.accessibilityIdentifier = @"history.empty";
    self.view = self.tableView;
}
- (void)viewDidLoad {
    [super viewDidLoad]; self.title = NSLocalizedString(@"History", nil);
    [self reloadHistory];
}
- (void)viewWillAppear:(BOOL)animated { [super viewWillAppear:animated]; [self reloadHistory]; }
- (void)reloadHistory {
    QRHistoryStore *store = [AppDelegate appDelegate].historyStore;
    if (!store.context) { [self showError]; return; }
    NSFetchRequest *request = [NSFetchRequest fetchRequestWithEntityName:@"URLEntity"];
    request.sortDescriptors = @[[NSSortDescriptor sortDescriptorWithKey:@"createDate" ascending:NO]];
    request.fetchBatchSize = 40;
    self.fetchedResultsController = [[NSFetchedResultsController alloc] initWithFetchRequest:request managedObjectContext:store.context sectionNameKeyPath:nil cacheName:nil];
    self.fetchedResultsController.delegate = self;
    NSError *error;
    if (![self.fetchedResultsController performFetch:&error]) { [self showError]; return; }
    [self.tableView reloadData]; [self updateEmptyState];
}
- (void)showError {
    self.emptyLabel.text = NSLocalizedString(@"History could not be loaded. Your saved data has not been erased. Please restart the app and try again.", nil);
    self.tableView.backgroundView = self.emptyLabel;
}
- (void)updateEmptyState {
    self.emptyLabel.text = NSLocalizedString(@"No saved QR codes yet.\nScan a QR code to add it here.", nil);
    self.tableView.backgroundView = self.fetchedResultsController.fetchedObjects.count ? nil : self.emptyLabel;
}
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return self.fetchedResultsController.fetchedObjects.count; }
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:@"urlCell" forIndexPath:indexPath];
    URLEntity *record = [self.fetchedResultsController objectAtIndexPath:indexPath];
    UIListContentConfiguration *content = cell.defaultContentConfiguration;
    content.text = record.url;
    content.textProperties.numberOfLines = 0;
    content.textProperties.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    content.secondaryText = record.createDate ? [NSDateFormatter localizedStringFromDate:record.createDate dateStyle:NSDateFormatterMediumStyle timeStyle:NSDateFormatterShortStyle] : nil;
    content.image = [UIImage systemImageNamed:[record.url isURL] ? @"link" : @"text.alignleft"];
    cell.contentConfiguration = content;
    cell.accessibilityIdentifier = @"history.record";
    return cell;
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    URLEntity *record = [self.fetchedResultsController objectAtIndexPath:indexPath];
    if (self.selectedPayloadHandler && record.url.length) { self.selectedPayloadHandler(record.url); return; }
    if (self.presentedViewController) return;
    QRPhoneResultViewController *result = [[QRPhoneResultViewController alloc] initWithPayload:record.url ?: @"" openWebsiteHandler:^(NSURL *URL) {
        [UIApplication.sharedApplication openURL:URL options:@{} completionHandler:^(BOOL success) {
            if (!success) [self showMessage:NSLocalizedString(@"This website could not be opened.", nil)];
        }];
    }];
    [self presentViewController:result animated:YES completion:nil];
}
- (void)showMessage:(NSString *)message {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:NSLocalizedString(@"History", nil) message:message preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:NSLocalizedString(@"OK", nil) style:UIAlertActionStyleDefault handler:nil]];
    [self presentViewController:alert animated:YES completion:nil];
}
- (void)tableView:(UITableView *)tableView commitEditingStyle:(UITableViewCellEditingStyle)style forRowAtIndexPath:(NSIndexPath *)indexPath {
    if (style != UITableViewCellEditingStyleDelete) return;
    QRHistoryStore *store = [AppDelegate appDelegate].historyStore;
    [store.context deleteObject:[self.fetchedResultsController objectAtIndexPath:indexPath]];
    NSError *error;
    if (![store save:&error]) {
        [store.context rollback];
        [self showMessage:NSLocalizedString(@"The record could not be deleted. Please try again.", nil)];
    }
}
- (void)controllerDidChangeContent:(NSFetchedResultsController *)controller { [self.tableView reloadData]; [self updateEmptyState]; }
@end
