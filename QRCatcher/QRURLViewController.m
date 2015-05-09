//
//  QRURLViewController.m
//  QRCatcher
//
//  Created by Mango on 15/4/7.
//  Copyright (c) 2015年 Mango. All rights reserved.
//

#import "QRURLViewController.h"
#import "AppDelegate.h"
//view
#import "QRURLTableViewCell.h"
//model
#import "URLEntity.h"
//tools
#import "NSString+Tools.h"

@interface QRURLViewController ()<UITableViewDataSource,UITableViewDelegate,NSFetchedResultsControllerDelegate>

@property (nonatomic,strong) NSFetchedResultsController *fetchedResultsController;
@property (weak, nonatomic) IBOutlet UITableView *tableView;

@end

static NSString *urlCell = @"urlCell";

@implementation QRURLViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    
    [self setupNSFetchedResultsController];
}

- (void)didReceiveMemoryWarning {
    [super didReceiveMemoryWarning];
    // Dispose of any resources that can be recreated.
}

#pragma mark - view did load setup
- (void)setupNSFetchedResultsController
{
    NSSortDescriptor *sortDescriptor = [NSSortDescriptor sortDescriptorWithKey:@"createDate" ascending:YES];
    NSFetchRequest *requst = [NSFetchRequest fetchRequestWithEntityName:@"URLEntity"];
    requst.sortDescriptors = @[sortDescriptor];
    NSManagedObjectContext *cotext = [[AppDelegate appDelegate] managedObjectContext];
    
    
    self.fetchedResultsController = [[NSFetchedResultsController alloc]initWithFetchRequest:requst managedObjectContext:cotext sectionNameKeyPath:nil cacheName:nil];
    self.fetchedResultsController.delegate = self;
    NSError *error = nil;
    [self.fetchedResultsController performFetch:&error];
    
    if (error) {
        NSLog(@"Unable to perform fetch.");
        NSLog(@"%@, %@", error, error.localizedDescription);
    }
}

#pragma mark - Table view data source
- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView
{
    return self.fetchedResultsController.sections.count;
}

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section
{
    if (self.fetchedResultsController.sections.count > 0)
    {
        id <NSFetchedResultsSectionInfo> sectionInfo = [self.fetchedResultsController.sections objectAtIndex:section];
        return [sectionInfo numberOfObjects];
    }
    else
        return 0;
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    
    QRURLTableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:urlCell];
    [self configureCell:cell atIndexPath:indexPath];
    return cell;
}

- (void)configureCell:(QRURLTableViewCell *)cell atIndexPath:(NSIndexPath *)indexPath {
    
    //setup cell
    cell.textLabel.textColor = [UIColor colorWithRed:65/225.0 green:182/255.0 blue:251 alpha:1];
    cell.imageView.image = [UIImage imageNamed:@"website2x"];
    cell.backgroundColor = [UIColor blackColor];

    // Fetch Record
    URLEntity *record = [self.fetchedResultsController objectAtIndexPath:indexPath];
    
    // Update Cell
    cell.textLabel.text = record.url;
}

#pragma mark - Table view delegate
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath
{
    URLEntity *record = [self.fetchedResultsController objectAtIndexPath:indexPath];
    [[UIApplication sharedApplication] openURL:[NSString HTTPURLFromString:record.url]];
}



- (BOOL)tableView:(UITableView *)tableView canEditRowAtIndexPath:(NSIndexPath *)indexPath
{
    return YES;
}

- (void)tableView:(UITableView *)tableView commitEditingStyle:(UITableViewCellEditingStyle)editingStyle forRowAtIndexPath:(NSIndexPath *)indexPath
{
    if (editingStyle == UITableViewCellEditingStyleDelete)
    {
        NSManagedObjectContext *context = [[AppDelegate appDelegate]managedObjectContext];
        URLEntity *entity = [self.fetchedResultsController objectAtIndexPath:indexPath];
        [context deleteObject:entity];
    }
}


#pragma mark - NSFetchedResultsController delegate

- (void)controllerWillChangeContent:(NSFetchedResultsController *)controller
{
    [self.tableView beginUpdates];
}

- (void)controllerDidChangeContent:(NSFetchedResultsController *)controller
{
    [self.tableView endUpdates];
}

- (void)controller:(NSFetchedResultsController *)controller didChangeObject:(id)anObject
       atIndexPath:(NSIndexPath *)indexPath forChangeType:(NSFetchedResultsChangeType)type
      newIndexPath:(NSIndexPath *)newIndexPath {
    
    UITableView *tableView = self.tableView;
    
    switch(type) {
            
        case NSFetchedResultsChangeInsert:
            [tableView insertRowsAtIndexPaths:[NSArray arrayWithObject:newIndexPath]
                             withRowAnimation:UITableViewRowAnimationFade];
            break;
            
        case NSFetchedResultsChangeDelete:
            [tableView deleteRowsAtIndexPaths:[NSArray arrayWithObject:indexPath]
                             withRowAnimation:UITableViewRowAnimationFade];
            break;
            
        case NSFetchedResultsChangeUpdate:
            [self configureCell:(QRURLTableViewCell*)[tableView cellForRowAtIndexPath:indexPath]
                    atIndexPath:indexPath];
            break;
            
        case NSFetchedResultsChangeMove:
            [tableView deleteRowsAtIndexPaths:[NSArray arrayWithObject:indexPath]
                             withRowAnimation:UITableViewRowAnimationFade];
            [tableView insertRowsAtIndexPaths:[NSArray arrayWithObject:newIndexPath]
                             withRowAnimation:UITableViewRowAnimationFade];
            break;
    }
}

/*
#pragma mark - Navigation

// In a storyboard-based application, you will often want to do a little preparation before navigation
- (void)prepareForSegue:(UIStoryboardSegue *)segue sender:(id)sender {
    // Get the new view controller using [segue destinationViewController].
    // Pass the selected object to the new view controller.
}
*/

@end
